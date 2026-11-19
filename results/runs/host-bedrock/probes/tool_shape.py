import copy, json
from pbe.runner import agent, llm
tools = agent.tools(agent.TEST_CONDITION)

def as_list(tools):
    """params rewritten from a free-named map (additionalProperties) to a list of entries with fixed fields."""
    out = copy.deepcopy(tools)
    for t in out:
        props = t["function"]["parameters"].get("properties", {})
        if "params" in props and "additionalProperties" in props["params"]:
            entry = copy.deepcopy(props["params"]["additionalProperties"])
            entry["properties"] = {"name": {"type": "string", "description": "The parameter's name, e.g. od"}, **entry["properties"]}
            entry["required"] = ["name"] + entry.get("required", [])
            props["params"] = {"type": "array", "items": entry, "description": props["params"].get("description", "")}
    return out

q = ("Don't call any tool. Answer in plain text: for submit_design, what does `params` look like? List the fields each "
     "entry requires, and the exact allowed values of `kind`. Say 'not given' for anything your tool definitions don't tell you.")
for label, ts in [("as now (map)", tools), ("rewritten (list)", as_list(tools))]:
    for host in ["amazon-bedrock", "openai"]:
        r = llm.chat("openai/gpt-6.2-sol", [{"role": "user", "content": q}], tools=ts, max_tokens=3000,
                     provider={"only": [host], "allow_fallbacks": False})
        u = r["usage"]
        print(f"== {label} on {r.get('provider')}: prompt tokens {u['prompt_tokens']}, ${u['cost']:.4f}")
        print((r["choices"][0]["message"].get("content") or "")[:400])
