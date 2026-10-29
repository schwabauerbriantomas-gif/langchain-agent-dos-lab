"""Batería 3 — Borrado vs espacio real (espejo F-014 de n8n).

En n8n: borrar executions por API devolvía 0 bytes (freelist de SQLite);
solo VACUUM OFFLINE recupera. Acá: DELETE /history/{sid} sobre una sesión
floodeada -> medir bytes reales recuperados -> VACUUM -> medir de nuevo.
"""
import httpx
from lab_common import BASE, db_bytes, freelist_pages, save

results = {}
results["db_before_delete"] = db_bytes()
results["pragmas_before"] = freelist_pages()

# flood_s2 fue floodeada en battery1 (5 x 600KB)
with httpx.Client(timeout=60.0) as c:
    r = c.request("DELETE", f"{BASE}/history/flood_s2")
    results["delete_response"] = r.json()

results["db_after_delete"] = db_bytes()
results["pragmas_after_delete"] = freelist_pages()
results["reclaimed_by_delete_bytes"] = (
    results["db_before_delete"] - results["db_after_delete"])

# VACUUM offline (server sigue vivo pero sin tráfico; conexión aparte)
import sqlite3
from lab_common import DB
conn = sqlite3.connect(DB)
conn.execute("VACUUM")
conn.close()

results["db_after_vacuum"] = db_bytes()
results["pragmas_after_vacuum"] = freelist_pages()
results["reclaimed_by_vacuum_bytes"] = (
    results["db_after_delete"] - results["db_after_vacuum"])

save("battery3_delete_vacuum.json", results)
print(f"db: {results['db_before_delete']} -> delete->{results['db_after_delete']} "
      f"-> vacuum->{results['db_after_vacuum']}")
print(f"recuperado por delete: {results['reclaimed_by_delete_bytes']} | "
      f"por VACUUM: {results['reclaimed_by_vacuum_bytes']}")
