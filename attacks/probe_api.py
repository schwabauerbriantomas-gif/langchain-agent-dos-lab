"""Direct probe to the LLM API: how does the provider treat a ~600KB payload
(outside the victim). Reproduces the finding that the provider accepts
~105k prompt tokens without a context-based rejection (run: 2026-10-29).

Credentials: export LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL).
"""
import time
import random
import os
import httpx

key = os.environ["LLM_API_KEY"]
BASE = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
MODEL = os.environ.get("LLM_MODEL", "glm-5.3-flash")

words = "pedido factura cliente envio reclamo producto stock pago remito cuota interes vencimiento sucursal camion horario atencion sistema error".split()
text = " ".join(" ".join(random.Random(7).choices(words, k=12)) for _ in range(2300))
print("payload bytes:", len(text.encode()))

t0 = time.time()
try:
    r = httpx.post(f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": MODEL, "max_tokens": 16,
              "messages": [{"role": "user", "content": text}]},
        timeout=240.0)
    dt = time.time() - t0
    body = r.json()
    err = body.get("error")
    ch = (body.get("choices") or [{}])[0]
    msg = (ch.get("message") or {})
    print(f"status={r.status_code} dt={dt:.1f}s")
    print("error:", str(err)[:300])
    print("finish_reason:", ch.get("finish_reason"))
    print("content_len:", len(msg.get("content") or ""))
    print("usage:", body.get("usage"))
except Exception as e:
    print(f"EXC {type(e).__name__}: {e} dt={time.time()-t0:.1f}s")
