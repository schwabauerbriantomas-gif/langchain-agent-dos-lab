# Methodology

Run date: **2026-10-29**. Everything ran on one machine: Ubuntu 24.04.1 LTS under WSL2 (kernel 6.18.54.1-microsoft-standard-WSL2), Python **3.14.7**, venv on ext4.

## 1. Threat model

- The attacker can send arbitrary-size text as a chat message and chooses the `session_id` (the LangGraph `thread_id`). No authentication (mirrors a public support widget).
- Goal: measure damage the attacker can do to **server resources** (disk, memory) through the agent's *persistence layer*, and compare against the same attack applied to an n8n deployment in a prior lab.
- The LLM is part of the attacked system: attack scripts **never talk to the LLM API directly** — only to the victim's HTTP endpoint. (The optional `probe_*.py` scripts are the exception: they characterize the provider itself and are labeled as such.)

## 2. Victim (mirrors the docs deployment pattern)

`victim/victim_app.py` — FastAPI on `127.0.0.1:8124`:

| Component | Choice | Rationale |
|---|---|---|
| Agent | `langchain.agents.create_agent(model, tools=[], checkpointer=saver)` | Minimal docs-style pattern; tools are orthogonal to persistence |
| Checkpointer | `SqliteSaver` (`langgraph-checkpoint-sqlite 3.1.2`) | The default persistence choice for single-process deployments |
| Thread ID | attacker-supplied `session_id` | Standard session-keyed memory |
| LLM | `langchain_openai.ChatOpenAI` against an OpenAI-compatible endpoint (glm-5.3-flash), `max_tokens=4096`, `timeout=90`, `max_retries=1` | The 4096 cap removes the "reasoning burns all tokens" confounder from the n8n lab |
| Memory envelope | `RLIMIT_AS = 2.5 GB` via `victim/server_wrapper.py` | Same envelope as the n8n lab's 2.5 GB heap, so heap results are comparable |
| Extra endpoint | `GET /history/{sid}` (full `get_tuple` deserialize in the server process) and `DELETE /history/{sid}` (direct SQLite delete) | The analogues of n8n's "list executions with `includeData=true`" and "delete execution" |

The adversarial analogue of n8n's execution-log read path is *any* code path that loads full thread state into the main process — `GET /history` makes it explicit and measurable.

## 3. Payload

`payload_text(size_bytes, seed)` in `attacks/lab_common.py`: deterministic (seeded `random.Random`), realistic word stream (~18-word vocabulary, 12 words per line), truncated to the exact byte size. Deterministic seeds make every run byte-reproducible.

## 4. Batteries

### Battery 1 — storage flood (`attacks/battery1_storage_flood.py`)
6 sessions × 5 messages × 600 KB = 18.4 MB total input (identical totals to the n8n lab). After **every** request it records: HTTP status, latency, output length, finish reason, error, and total DB size (sqlite + wal + shm). Ends with a `GET /history` of one flooded session to prove persistence regardless of LLM outcome. Metrics: DB growth and amplification factor (growth ÷ input).

### Battery 2 — heap / full-state load (`attacks/battery2_heap.py`)
Phase A: flood one fresh session (`heap_victim`) with 10 × 600 KB, sampling the server's `VmRSS`/`VmHWM` from `/proc/<pid>/status` after each message. Phase B: the actual n8n analogue — `GET /history` of **all** 7 flooded sessions (~24.6 MB of attacker text), 3 full rounds, watching whether memory accumulates and whether the server survives. Server death is detected by PID disappearance.

### Battery 3 — delete vs reclaimed space (`attacks/battery3_delete_vacuum.py`)
Record DB size + `PRAGMA freelist_count`/`page_count` → `DELETE /history/flood_s2` → record again (bytes reclaimed by delete) → `VACUUM` from a separate connection → `PRAGMA wal_checkpoint(TRUNCATE)` → final size (bytes reclaimed by vacuum).

### Battery 4 — empty-success threshold (`attacks/battery4_f005.py`)
Sizes 1, 2, 4, 8, 16, 32 KB into fresh sessions; classifies each outcome as normal reply / **empty-success** (HTTP 200, `output_len == 0`, no error, i.e. the F-005 pattern) / timeout. Comparison threshold from the n8n lab: ~8 KB.

### Provider probes (optional)
- `attacks/probe_api.py`: one ~600 KB request straight to the provider (does it reject by context length? how long does it take?). Result of the run: accepted ~105k prompt tokens, no context-based rejection.
- `attacks/probe_thinking.py`: same 8 KB payload with `thinking` disabled vs enabled. Result: persistence-side findings are unaffected (writes happen pre-LLM); thinking OFF makes each flood request 4–10 s instead of ~3.5 min.

### Consolidation
`attacks/consolidate.py` regenerates `evidence/COMPARATIVA_N8N.json` from the four battery JSONs: veredicts are computed from the measured numbers only (no manual grading), with the n8n reference values inlined from the prior lab.

## 5. Rigor rules and measurement gotchas

Rules that materially changed the outcome during the run:

1. **WAL inflates post-VACUUM reads.** Reading the DB file immediately after `VACUUM` showed 494 MB (larger than before!). `VACUUM` writes through the WAL. Always finish with `PRAGMA wal_checkpoint(TRUNCATE)` and then measure (real: 246.6 MB).
2. **DELETE is a freelist operation.** `page_count` is unchanged (67,620 before and after delete); `freelist_count` rises to 7,544 — the file never shrinks. Any "we delete old sessions" defense must also schedule `VACUUM`.
3. **Block-buffered logs.** Long batteries run with `python -u`; otherwise `> battery.log` shows nothing until exit.
4. **Killing the wrapper by pattern kills your own shell** (`pkill -f server_wrapper.py` matches the invoking command line). Use `ps aux | grep "[s]erver_wrapper"`.
5. **LLM latency is not part of the storage finding.** Input is checkpointed before inference; the amplify-then-fail case (LLM slow or erroring) is *included* in battery 1 by design.
6. Every claim in the README maps to a field in a committed evidence JSON — no numbers are hand-copied.

## 6. Exact software versions (from the run's venv)

| Package | Version |
|---|---|
| langchain | 1.4.7 |
| langchain-core | 1.7.1 |
| langchain-openai | 1.7.3 |
| langgraph | 1.2.18 |
| langgraph-checkpoint | 4.3.1 |
| langgraph-checkpoint-sqlite | 3.1.2 |
| langgraph-prebuilt | 1.1.1 |
| openai (client) | 3.41.0 |
| pydantic | 2.14.1 |
| fastapi | 0.162.0 |
| starlette | 1.10.0 |
| uvicorn | 0.54.0 |
| httpx | 0.28.1 |
| ormsgpack | 1.13.0 |
| Python | 3.14.7 |
| Model | glm-5.3-flash (OpenAI-compatible endpoint) |

`requirements.txt` pins the direct dependencies to exactly these versions.

## 7. Key numbers, one screen

```
Battery 1  input 18,432,000 B -> DB growth 192,363,840 B   amplification 10.436x
           (n8n reference: 2.3x linear)
           flood_s1 persisted despite any LLM outcome: 10 messages, 3,085,083 chars
Battery 2  all-sessions full-state load x3 rounds: server alive, VmHWM 234,768 kB
           (n8n reference: fatal OOM at 2.5 GB with 2 x 600 KB)
Battery 3  delete reclaims 0 B (freelist 0 -> 7,544 pages, page_count unchanged)
           VACUUM + wal_checkpoint(TRUNCATE): 37,948,144 B reclaimed
           (post-VACUUM pre-drain read: 494,158,368 B -- WAL artifact, see gotcha 1)
Battery 4  empty-successes: 0 of 6 runs (max_tokens=4096)
           LLM server-side timeouts: 2,048 / 4,096 / 8,192 / 16,384 B (~190 s each)
           (n8n reference: empty-success from ~8 KB via reasoning-token exhaustion)
```
