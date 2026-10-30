"""Helpers comunes de las baterías (lado atacante)."""
import json
import os
import random
import sqlite3

BASE = "http://127.0.0.1:8124"
LAB = os.path.dirname(os.path.abspath(__file__))
EVIDENCE = os.path.join(LAB, "evidence")
REPO_ROOT = os.path.dirname(LAB)
DATA_DIR = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
# Same default DB file the victim writes to (victim/victim_app.py), so db_bytes()
# measures the live database regardless of the cwd each component was started from.
DB = os.environ.get("VICTIM_DB", os.path.join(DATA_DIR, "victim_chat.sqlite"))
os.makedirs(EVIDENCE, exist_ok=True)


def db_bytes():
    total = 0
    for suffix in ["", "-wal", "-shm"]:
        p = DB + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


def server_pid():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().decode(errors="replace")
            if "server_wrapper.py" in cmd:
                return int(pid)
        except OSError:
            continue
    return None


def rss_kb(pid):
    out = {}
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith(("VmRSS", "VmHWM")):
                k, v = line.split(":")
                out[k] = int(v.strip().split()[0])
    return out


def payload_text(size_bytes, seed=42):
    """Texto realista tokenizable (palabras), determinista."""
    rng = random.Random(seed)
    words = ["pedido", "factura", "cliente", "envio", "reclamo", "producto",
             "stock", "pago", "remito", "cuota", "interes", "vencimiento",
             "sucursal", "camion", "horario", "atencion", "sistema", "error"]
    parts = []
    n = 0
    while n < size_bytes:
        line = " ".join(rng.choices(words, k=12))
        parts.append(line)
        n += len(line) + 1
    return "\n".join(parts)[:size_bytes]


def save(name, data):
    path = os.path.join(EVIDENCE, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"[saved] {path}")


def freelist_pages():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("PRAGMA freelist_count")
    free = cur.fetchone()[0]
    cur.execute("PRAGMA page_count")
    pages = cur.fetchone()[0]
    conn.close()
    return {"freelist_pages": free, "page_count": pages,
            "page_size": 4096}
