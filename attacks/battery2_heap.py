"""Batería 2 — Heap (espejo F-013 de n8n).

En n8n: ~30 execs grandes parseados con includeData=true en el proceso MAIN
-> FATAL ERROR heap limit (heap 2.5GB). Acá el análogo es GET /history/{sid}
(el endpoint que deserializa el checkpoint COMPLETO en el proceso del server,
bajo RLIMIT_AS 2.5GB, mismo envelope que el heap de n8n).

Fase A: flood una sola sesión con ~30 x 600KB (18MB).
Fase B: GET /history repetido, midiendo VmRSS/VmHWM del server.
"""
import httpx
from lab_common import BASE, db_bytes, payload_text, rss_kb, save, server_pid

SIZE = 600 * 1024
N_MSGS = 10  # heap_victim: 6MB propios; el vector real se prueba cargando
             # TODAS las sesiones floodeadas (battery1: 18MB) — análogo de
             # listar ~30 execs con includeData en el proceso main
SID = "heap_victim"
LOAD_TARGETS = ["heap_victim"] + [f"flood_s{i}" for i in range(1, 7)]

results = {"size_bytes": SIZE, "n_msgs": N_MSGS, "session": SID}
pid = server_pid()
assert pid, "server no encontrado"
results["server_pid"] = pid
results["rss_before_kb"] = rss_kb(pid)
print(f"server pid={pid} rss_before={results['rss_before_kb']}")

sent = 0
latencies = []
with httpx.Client(timeout=600.0) as c:
    for i in range(N_MSGS):
        text = payload_text(SIZE, seed=1000 + i)
        sent += len(text.encode())
        r = c.post(f"{BASE}/chat", json={"session_id": SID, "message": text})
        latencies.append(r.elapsed.total_seconds())
        rss = rss_kb(pid)
        print(f"msg {i+1}/{N_MSGS} http={r.status_code} "
              f"db={db_bytes()} VmRSS={rss.get('VmRSS')}kB VmHWM={rss.get('VmHWM')}kB")
        results.setdefault("rss_trace", []).append(
            {"i": i, "db_bytes": db_bytes(), **rss})

results["total_sent_bytes"] = sent
results["rss_after_flood_kb"] = rss_kb(pid)

# Fase B: el vector real de n8n era el PARSEO de toda esa data en el proceso main.
# Carga secuencial de TODAS las sesiones floodeadas (~24MB de texto atacante),
# 3 rondas, midiendo si la memoria ACUMULA en el proceso principal.
with httpx.Client(timeout=600.0) as c:
    for attempt in range(3):
        for target in LOAD_TARGETS:
            try:
                r = c.get(f"{BASE}/history/{target}")
                body = r.json()
            except Exception as e:
                body = {"client_error": f"{type(e).__name__}: {e}"}
            rss = rss_kb(pid) if server_pid() else None
            results.setdefault("history_loads", []).append(
                {"attempt": attempt, "target": target,
                 "status": getattr(r, "status_code", None),
                 "body": body, "rss": rss})
            print(f"load r{attempt+1} {target}: {body} rss={rss}")
            if server_pid() is None:
                results["server_alive_after_loads"] = False
                print("SERVER MUERTO tras loads")
                break
        if server_pid() is None:
            break

if server_pid():
    results["server_alive_after_loads"] = True
    results["rss_final_kb"] = rss_kb(server_pid())

save("battery2_heap.json", results)
print(f"\nVmHWM final: {results.get('rss_final_kb', results['rss_after_flood_kb'])}")
