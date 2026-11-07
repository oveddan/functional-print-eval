"""Prompt caching (issue 34): asking for it changes the price, never what the model reads.

Claude models get one top-level `cache_control` field. Every message and tool sent stays byte
for byte what any other model gets, in every condition, and each trial records whether
caching was asked for.
"""
import json
import urllib.request

import pytest

from pbe.runner import agent, llm, tasks
from pbe.runner.trial_record import CodeSettings, ModelCall

CLAUDE = "anthropic/claude-haiku-5.5"
OTHERS = ["openai/gpt-6.1-sol", "google/gemini-4-argon", "deepseek/deepseek-v4-pro-0813"]
ANY_OTHER = OTHERS[0]  # what's posted doesn't depend on which other model it is


class NoCodeTool:
    """Stands in for run_python, so can_run_code's prompt and tools are compared without a sandbox."""
    settings = CodeSettings(sandbox="none (test)", timeout_s=1, trial_s=1, output_chars=1)

    def prompt_line(self):
        return "- run_python(code): run Python."


def requests_sent(model, condition, monkeypatch):
    """Every request one scripted trial sends: (messages, tools, the other request fields) as JSON text."""
    monkeypatch.setattr(agent, "code_tool", lambda task, condition, workdir: NoCodeTool() if condition == "can_run_code" else None)
    sent = []

    def chat(model, messages, tools=None, max_tokens=None, **params):
        sent.append((json.dumps(messages), json.dumps(tools), params))
        tool_call = {"id": "1", "type": "function", "function": {"name": "measure", "arguments": '{"item": "a", "what": "b"}'}}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [tool_call]}}]}
    record, _, _ = agent.run_trial(tasks.load("tripod-plate"), model, condition, max_turns=3, chat=chat)
    return sent, record


# each condition once and each other model once: what a model reads doesn't depend on the pair
@pytest.mark.parametrize("condition, other", list(zip(agent.CONDITIONS, OTHERS, strict=True)))
def test_claude_reads_exactly_what_every_other_model_reads(condition, other, monkeypatch):
    claude_sent, claude_record = requests_sent(CLAUDE, condition, monkeypatch)
    other_sent, other_record = requests_sent(other, condition, monkeypatch)
    assert len(claude_sent) == len(other_sent) == 3
    for (claude_messages, claude_tools, claude_params), (messages, tools, params) in zip(claude_sent, other_sent):
        assert claude_messages == messages and claude_tools == tools
        assert claude_params == {"cache_control": {"type": "ephemeral"}} and params == {}
    assert claude_record.settings.prompt_caching is True and other_record.settings.prompt_caching is False


def body_posted(model, monkeypatch):
    """The request body llm.chat posts to OpenRouter for this model."""
    posted = []

    def urlopen(request, timeout=None):
        posted.append(request.data)
        raise ConnectionResetError("stop here")
    monkeypatch.setattr(llm, "_key", lambda: "fake")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    tools = agent.tools("can_ask")
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    with pytest.raises(llm.LLMError):
        llm.chat(model, messages, tools=tools, retries=0, max_tokens=10, **llm.caching_params(model))
    return json.loads(posted[0])


def test_the_body_differs_only_by_the_model_and_the_top_level_cache_field(monkeypatch):
    claude_body = body_posted(CLAUDE, monkeypatch)
    other_body = body_posted(ANY_OTHER, monkeypatch)
    assert claude_body.pop("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in other_body
    assert claude_body.pop("model") == CLAUDE and other_body.pop("model") == ANY_OTHER
    assert json.dumps(claude_body) == json.dumps(other_body)


def test_only_claude_models_ask_for_caching():
    assert llm.requests_caching("anthropic/claude-opus-5.5") and llm.requests_caching("anthropic/claude-sonnet-5.5")
    assert not any(llm.requests_caching(model) for model in OTHERS)


def test_a_call_reads_the_providers_cached_token_counts():
    usage = {"prompt_tokens": 1000, "cost": 0.01, "prompt_tokens_details": {"cached_tokens": 900, "cache_write_tokens": 80}}
    call = ModelCall(model=CLAUDE, provider="p", finish_reason="tool_calls", usage=usage, elapsed_s=1.0)
    assert (call.prompt_tokens, call.cached_tokens, call.cache_write_tokens) == (1000, 900, 80)
    silent = ModelCall(model="m", provider=None, finish_reason=None, usage=None, elapsed_s=None)
    assert (silent.prompt_tokens, silent.cached_tokens, silent.cache_write_tokens) == (0, 0, 0)
