"""OpenRouter chat client.

The key is read from 1Password at run time, or from OPENROUTER_API_KEY for anyone
reproducing the runs with their own key. It is never printed or saved. In a cloud
session the variable holds a placeholder, and the proxy attaches the real key.
"""
import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from functools import cache

from pydantic import BaseModel

URL = "https://openrouter.ai/api/v1/chat/completions"
OP_REF = "op://kb-sync/OpenRouter/credential"
RETRYABLE = {408, 429, 500, 502, 503, 504}
# Anthropic's automatic prompt caching, as OpenRouter documents it (docs/guides/best-practices/prompt-caching,
# read 2026-11-04): one top-level field, so the messages and tools sent stay byte for byte what they were.
# The default 5-minute cache: every saved Claude turn came back in under 75 s. Other providers cache on their own.
AUTOMATIC_CACHE = {"type": "ephemeral"}


class LLMError(RuntimeError):
    pass


@cache
def _key():
    if key := os.environ.get("OPENROUTER_API_KEY"):
        return key
    op_read = subprocess.run(["op", "read", OP_REF], capture_output=True, text=True)
    if op_read.returncode != 0:
        raise LLMError(f"no OPENROUTER_API_KEY, and `op read {OP_REF}` failed: {op_read.stderr.strip()}")
    return op_read.stdout.strip()


def _post(data, timeout) -> dict:
    request = urllib.request.Request(URL, data=data, headers={
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
        "X-Title": "print-build-eval",
    })
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.load(reply)


def _error_in(response):
    """OpenRouter can answer 200 with an error in the body, at the top or in the first choice."""
    first_choice = (response.get("choices") or [{}])[0]
    return response.get("error") or first_choice.get("error")


class _Failed(Exception):
    """One request that failed, and what failed: an HTTP status, the connection, or an error in the body."""

    def __init__(self, message, http_code=None, body_error=None, connection=False):
        super().__init__(message)
        self.http_code, self.body_error, self.connection = http_code, body_error, connection

    @property
    def worth_retrying(self):
        if self.connection:
            return True
        if self.http_code is not None:
            return self.http_code in RETRYABLE
        return not self.body_error or self.body_error.get("code") in RETRYABLE


def _attempt(model, data, timeout) -> dict:
    """One request; raises _Failed."""
    started = time.monotonic()
    try:
        response = _post(data, timeout)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        raise _Failed(f"HTTP {e.code} from {model}: {detail}", http_code=e.code) from None
    except (OSError, http.client.HTTPException, ValueError) as e:  # a dropped connection, or a cut-off body
        raise _Failed(f"{model}: {e}", connection=True) from None
    error = _error_in(response)
    if error or not response.get("choices"):
        raise _Failed(f"{model}: {error or 'no choices in response'}", body_error=error)
    response["elapsed_s"] = round(time.monotonic() - started, 1)
    return response


def requests_caching(model) -> bool:
    """Whether calls to this model ask for prompt caching: Claude models only (issue 34)."""
    return model.startswith("anthropic/")


def caching_params(model) -> dict:
    """What a call adds to its request to ask for caching: a price change, never a change to what the model reads."""
    return {"cache_control": AUTOMATIC_CACHE} if requests_caching(model) else {}


def chat(model, messages, tools=None, retries=4, timeout=900, **params) -> dict:
    """One completion. Returns OpenRouter's response with `elapsed_s` added;
    `usage.cost` is what the call was charged, in USD."""
    body = {"model": model, "messages": messages, "usage": {"include": True}, **params}
    if tools:
        body["tools"] = tools
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        try:
            return _attempt(model, data, timeout)
        except _Failed as failure:
            if attempt == retries or not failure.worth_retrying:
                raise LLMError(str(failure)) from None
            time.sleep(5 * 2 ** attempt)


class FunctionCall(BaseModel):
    name: str
    arguments: str | None = None  # JSON text, as the model wrote it


class ToolCall(BaseModel):
    id: str
    function: FunctionCall


class Message(BaseModel):
    """The one part of the model's message the agent reads. The message itself is sent back as it came."""
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    message: dict
    finish_reason: str | None = None


class Reply(BaseModel):
    """What the agent reads from chat()'s response. A provider may leave out anything but the choices."""
    choices: list[Choice]
    model: str | None = None
    provider: str | None = None
    usage: dict | None = None  # its keys differ by provider; `cost` is the charge in USD
    elapsed_s: float | None = None

    @property
    def message(self) -> dict:
        return self.choices[0].message

    @property
    def finish_reason(self) -> str | None:
        return self.choices[0].finish_reason

    @property
    def tool_calls(self) -> list[ToolCall]:
        return Message.model_validate(self.message).tool_calls or []
