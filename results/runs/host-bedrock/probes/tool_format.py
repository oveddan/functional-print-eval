from pbe.runner import agent, llm
tools = agent.tools(agent.TEST_CONDITION)
q = ("Don't call any tool. Answer in plain text: 1) list the names of every tool you have. "
     "2) For submit_design, each entry in `params` is an object: list its required fields, and the exact allowed values of `kind`. "
     "Say 'not given' for anything your tool definitions don't tell you.")
for host in ["openai", "amazon-bedrock"]:
    for i in range(2):
        r = llm.chat("openai/gpt-6.2-sol", [{"role": "user", "content": q}], tools=tools, max_tokens=4000,
                     provider={"only": [host], "allow_fallbacks": False})
        u = r["usage"]
        print(f"== {host} #{i+1} served by {r.get('provider')}, reasoning {(u.get('completion_tokens_details') or {}).get('reasoning_tokens')}, prompt tokens {u['prompt_tokens']}, ${u['cost']:.4f}")
        print((r["choices"][0]["message"].get("content") or "")[:700])
