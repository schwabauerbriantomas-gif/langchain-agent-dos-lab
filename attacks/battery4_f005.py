"""Batería 4 — Outputs vacíos (espejo F-005 de n8n).

En n8n: glm-5.3-flash con inputs >= ~8KB quemaba TODO max_tokens en
reasoning y devolvía content='' con finish_reason=length; el workflow
reportaba success con output vacío. Acá: mismo modelo vía langchain,
tamaños crecientes, sesiones frescas.
"""
import httpx
from lab_common import BASE, payload_text, save

SIZES = [1024, 2048, 4096, 8192, 16384, 32768]
results = {"sizes": SIZES, "runs": []}

with httpx.Client(timeout=600.0) as c:
    for size in SIZES:
        sid = f"f005_{size}"
        text = payload_text(size, seed=size)
        r = c.post(f"{BASE}/chat", json={"session_id": sid, "message": text})
        body = r.json()
        usage = body.get("usage") or {}
        entry = {
            "input_bytes": size, "http_status": r.status_code,
            "output_len": len(body.get("output") or ""),
            "finish_reason": body.get("finish_reason"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": (usage.get("output_token_details") or {}).get("reasoning"),
            "elapsed_s": body.get("elapsed_s"),
            "error": (body.get("error") or "")[:200],
        }
        results["runs"].append(entry)
        print(f"{size}B -> out_len={entry['output_len']} "
              f"finish={entry['finish_reason']} tok={entry['output_tokens']} "
              f"(reasoning {entry['reasoning_tokens']}) {entry['elapsed_s']}s "
              f"err={entry['error'][:60]!r}")

empty = [r for r in results["runs"] if r["output_len"] == 0
         and r["http_status"] == 200 and not (r.get("error") or "")]
results["empty_success_threshold_bytes"] = (
    min(r["input_bytes"] for r in empty) if empty else None)
results["llm_timeout_sizes"] = [r["input_bytes"] for r in results["runs"]
                                if "Timeout" in (r.get("error") or "")]
save("battery4_f005.json", results)
print(f"\numbral de success-vacío: {results['empty_success_threshold_bytes']}")
