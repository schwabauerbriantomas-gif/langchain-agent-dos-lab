"""Batería 1 — Storage flood (espejo F-014 de n8n).

6 sesiones x 5 mensajes de ~600KB (18MB input total, igual que el lab n8n).
Mide: crecimiento de DB (sqlite+wal), amplificación, persistencia pese a
fallo del LLM, latencia.
"""
import httpx
from lab_common import BASE, db_bytes, payload_text, save

SIZE = 600 * 1024
SESSIONS = [f"flood_s{i}" for i in range(1, 7)]
MSGS_PER = 5

results = {"size_bytes": SIZE, "sessions": SESSIONS, "msgs_per_session": MSGS_PER,
           "requests": []}

baseline = db_bytes()
results["db_bytes_baseline"] = baseline
print(f"baseline DB: {baseline} bytes")

with httpx.Client(timeout=240.0) as c:
    total_sent = 0
    for sid in SESSIONS:
        for i in range(MSGS_PER):
            text = payload_text(SIZE, seed=hash((sid, i)) % (10**9))
            total_sent += len(text.encode())
            r = c.post(f"{BASE}/chat", json={"session_id": sid, "message": text})
            try:
                body = r.json()
            except Exception:
                body = {"raw": r.text[:500]}
            entry = {
                "session_id": sid, "idx": i, "req_bytes": len(text.encode()),
                "http_status": r.status_code, "elapsed_s": body.get("elapsed_s"),
                "output_len": len(body.get("output") or ""),
                "error": (body.get("error") or "")[:300],
                "finish_reason": body.get("finish_reason"),
                "db_bytes_after": db_bytes(),
            }
            results["requests"].append(entry)
            print(f"{sid}#{i} sent={entry['req_bytes']} http={r.status_code} "
                  f"err={entry['error'][:80]!r} db={entry['db_bytes_after']}")

results["total_payload_bytes"] = total_sent
results["db_bytes_final"] = db_bytes()
results["db_growth_bytes"] = results["db_bytes_final"] - baseline
results["amplification"] = round(results["db_growth_bytes"] / total_sent, 3) \
    if total_sent else None

# ¿persistió pese a fallo del LLM? cargar history de una sesión floodeada
with httpx.Client(timeout=120.0) as c:
    r = c.get(f"{BASE}/history/{SESSIONS[0]}")
    results["history_after_flood"] = r.json()

save("battery1_storage_flood.json", results)
print(f"\ngrowth={results['db_growth_bytes']} sent={total_sent} "
      f"amplification={results['amplification']}x")
print(f"history flood_s1: {results['history_after_flood']}")
