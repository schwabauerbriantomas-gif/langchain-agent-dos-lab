"""Probe: thinking ON vs OFF with an 8KB input (the F-005 threshold observed
in the prior n8n lab). Shows the persistence side of the DoS is independent
of reasoning (it happens pre-LLM), while thinking OFF makes the flood
faster: request completes in 4-10s vs ~3.5min burning reasoning tokens.

Credentials: export LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL).
Run: 2026-10-29.
"""
import time
import random
import os
import httpx

key = os.environ["LLM_API_KEY"]
BASE = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
MODEL = os.environ.get("LLM_MODEL", "glm-5.3-flash")

words = "pedido factura cliente envio reclamo producto stock pago remito cuota interes vencimiento sucursal camion horario atencion sistema error".split()
rng = random.Random(8192)
text = " ".join(" ".join(rng.choices(words, k=12)) for _ in range(90))
assert 7500 < len(text.encode()) < 9000, len(text.encode())
print(f"payload: {len(text.encode())} bytes")

for label, thinking in [("OFF (disabled)", {"type": "disabled"}),
                        ("ON (enabled)", {"type": "enabled"})]:
    t0 = time.time()
    try:
        r = httpx.post(f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": MODEL, "max_tokens": 4096,
                  "thinking": thinking,
                  "messages": [{"role": "user", "content": text + "\n\nSummarize in one sentence."}]},
            timeout=300.0)
        dt = time.time() - t0
        b = r.json()
        ch = (b.get("choices") or [{}])[0]
        msg = (ch.get("message") or {})
        u = b.get("usage") or {}
        det = (u.get("completion_tokens_details") or {})
        print(f"\n[{label}] status={r.status_code} dt={dt:.1f}s")
        print("  finish_reason:", ch.get("finish_reason"))
        print("  content_len:", len(msg.get("content") or ""))
        print("  completion_tokens:", u.get("completion_tokens"),
              "| reasoning:", det.get("reasoning_tokens"))
    except Exception as e:
        print(f"[{label}] EXC {type(e).__name__}: {e} dt={time.time()-t0:.1f}s")
