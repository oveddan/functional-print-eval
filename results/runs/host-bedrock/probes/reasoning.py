from pbe.runner import llm
q = "A 5.5 mm hex nut goes into a 3D-printed pocket. Printers shrink holes by about 0.1-0.2 mm. What pocket size across flats would you design, and why? Two sentences."
for host in ["openai", "amazon-bedrock"]:
    for effort in [None, "medium", "high"]:
        extra = {"reasoning": {"effort": effort}} if effort else {}
        r = llm.chat("openai/gpt-6.2-sol", [{"role": "user", "content": q}], max_tokens=4000,
                     provider={"only": [host], "allow_fallbacks": False}, **extra)
        u = r["usage"]
        print(f"{r.get('provider'):15} effort={effort!s:7} reasoning tokens {(u.get('completion_tokens_details') or {}).get('reasoning_tokens')}, output {u['completion_tokens']}, ${u['cost']:.4f}")
