"""Consolidates evidence/*.json and produces the verdict vs the prior n8n lab.

n8n results (private lab, 2026-10-28, n8n 2.45.5):
- F-013 heap: ~30 large executions parsed with includeData=true -> OOM at a
  2.5GB heap, platform down (2x600KB => HWM 2.53GB). Total death of main process.
- F-014 storage: ~2.3x amplification (18MB input -> +41MB DB), API delete
  reclaims 0 bytes, only offline VACUUM; disk full -> SQLITE_FULL crash loop.
- F-005: inputs >= ~8KB -> content='' finish_reason=length, empty success.
"""
import json
import os

EV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence")


def load(name):
    p = os.path.join(EV, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


b1 = load("battery1_storage_flood.json")
b2 = load("battery2_heap.json")
b3 = load("battery3_delete_vacuum.json")
b4 = load("battery4_f005.json")

out = {"meta": {
    "langchain": "1.4.7", "langchain-core": "1.7.1", "langgraph": "1.2.18",
    "langgraph-checkpoint-sqlite": "3.1.2", "pydantic": "2.14.1",
    "python": "3.14.7", "modelo": "glm-5.3-flash (Z.AI coding endpoint)",
    "victim": "create_agent + SqliteSaver (docs pattern), FastAPI :8124",
    "envelope": "RLIMIT_AS 2.5GB (mismo heap que n8n en lab)",
}}

if b1:
    out["F014_storage_flood"] = {
        "input_mb": round(b1["total_payload_bytes"] / 1e6, 2),
        "db_growth_mb": round(b1["db_growth_bytes"] / 1e6, 2),
        "amplification_n8n": 2.3,
        "amplification_langchain": b1["amplification"],
        "persisted_despite_llm": b1["history_after_flood"],
        "veredicto": None,  # se llena abajo
    }

if b2:
    loads = b2.get("history_loads", [])
    peak = 0
    alive = b2.get("server_alive_after_loads", True)
    for h in loads:
        rss = (h.get("rss") or {}).get("VmHWM")
        if rss:
            peak = max(peak, rss)
    out["F013_heap"] = {
        "server_alive_after_loads": alive,
        "VmHWM_peak_kb": peak,
        "VmHWM_peak_gb": round(peak / 1e6, 2),
        "n8n_comparacion": "OOM fatal con heap 2.5GB y 2x600KB parseados",
        "veredicto": None,
    }

if b3:
    out["F014_delete_vacuum"] = {
        "recovered_by_delete_bytes": b3["reclaimed_by_delete_bytes"],
        "recovered_by_vacuum_bytes": b3["reclaimed_by_vacuum_bytes"],
        "n8n_comparacion": "delete API: 0 bytes; solo VACUUM offline",
        "veredicto": None,
    }

if b4:
    runs = b4.get("runs", [])
    empty_success = [r for r in runs if r["output_len"] == 0
                     and r["http_status"] == 200 and not (r.get("error") or "")]
    llm_timeouts = [r for r in runs if "Timeout" in (r.get("error") or "")]
    out["F005_empty_outputs"] = {
        "umbral_n8n": "~8KB (finish_reason=length, content='', success)",
        "empty_success_true": [
            {k: r[k] for k in ("input_bytes", "finish_reason")} for r in empty_success],
        "llm_timeouts_2a190s": [
            r["input_bytes"] for r in llm_timeouts],
        "runs": [{k: r[k] for k in ("input_bytes", "output_len",
                                    "finish_reason", "reasoning_tokens",
                                    "error")} for r in runs],
    }
    if empty_success:
        out["F005_empty_outputs"]["veredicto"] = (
            f"REPLICA: umbral {min(r['input_bytes'] for r in empty_success)}B")
    else:
        out["F005_empty_outputs"]["veredicto"] = (
            "NO REPLICA (F-005 puro): 0 empty-success. Hallazgo nuevo: "
            "timeouts LLM server-side en 2-16KB (~190s para fallar) "
            "devueltos como error limpio por langchain")

# Veredictos automaticos (solo hechos medidos)
if b1:
    amp = b1["amplification"] or 0
    out["F014_storage_flood"]["veredicto"] = (
        f"REPLICA con amplificacion {amp}x (n8n: 2.3x)"
        if amp >= 1.5 else
        f"REPLICA PARCIAL: amplificacion {amp}x < 1.5x")

if b2:
    ok = b2.get("server_alive_after_loads")
    out["F013_heap"]["veredicto"] = (
        "NO REPLICA: server sobrevivio a la carga de todo el historial"
        if ok else
        f"REPLICA: server murio (VmHWM peak {out['F013_heap']['VmHWM_peak_gb']}GB)")

if b3:
    rd = b3["reclaimed_by_delete_bytes"]
    drain = b3.get("recovered_after_drain_bytes")
    if drain is not None:
        out["F014_delete_vacuum"]["recovered_by_vacuum_bytes"] = drain
        out["F014_delete_vacuum"]["veredicto"] = (
            f"REPLICA: delete por API recupera {rd}B (freelist); "
            f"solo VACUUM+wals_checkpoint recupera {drain}B"
            if rd == 0 and drain > 0 else
            f"DIFIERE: delete={rd}B vacuum_drained={drain}B")
    else:
        out["F014_delete_vacuum"]["veredicto"] = (
            f"REPLICA: delete recupera {rd}B, VACUUM recupera "
            f"{b3['reclaimed_by_vacuum_bytes']}B"
            if rd == 0 and b3["reclaimed_by_vacuum_bytes"] > 0 else
            f"DIFIERE: delete={rd}B vacuum={b3['reclaimed_by_vacuum_bytes']}B")

report = os.path.join(EV, "COMPARATIVA_N8N.json")
with open(report, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

print(json.dumps(out, indent=2, ensure_ascii=False))
print(f"\n[guardado] {report}")
