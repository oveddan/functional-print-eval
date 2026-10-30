"""OpenRouter chat client.

The key is read from 1Password at run time, or from OPENROUTER_API_KEY for anyone
reproducing the runs with their own key. It is never printed or saved.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from functools import cache

URL = "https://openrouter.ai/api/v1/chat/completions"
OP_REF = "op://kb-sync/OpenRouter/credential"
RETRYABLE = {408, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


@cache
def _key():
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    r = subprocess.run(["op", "read", OP_REF], capture_output=True, text=True)
    if r.returncode != 0:
        raise LLMError(f"no OPENROUTER_API_KEY, and `op read {OP_REF}` failed: {r.stderr.strip()}")
    return r.stdout.strip()


def chat(model, messages, tools=None, retries=4, timeout=900, **params) -> dict:
    """One completion. Returns OpenRouter's response with `elapsed_s` added;
    `usage.cost` is what the call was charged, in USD."""
    body = {"model": model, "messages": messages, "usage": {"include": True}, **params}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        wait = 5 * 2 ** attempt
        req = urllib.request.Request(URL, data=data, headers={
            "Authorization": f"Bearer {_key()}",
            "Content-Type": "application/json",
            "X-Title": "print-build-eval",
        })
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:2000]
            if e.code in RETRYABLE and attempt < retries:
                time.sleep(wait)
                continue
            raise LLMError(f"HTTP {e.code} from {model}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(wait)
                continue
            raise LLMError(f"{model}: {e}") from None
        # OpenRouter can answer 200 with an error in the body
        err = resp.get("error") or (resp.get("choices") or [{}])[0].get("error")
        if err or not resp.get("choices"):
            if attempt < retries and (not err or err.get("code") in RETRYABLE):
                time.sleep(wait)
                continue
            raise LLMError(f"{model}: {err or 'no choices in response'}")
        resp["elapsed_s"] = round(time.monotonic() - t0, 1)
        return resp
