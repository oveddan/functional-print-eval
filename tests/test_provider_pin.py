"""Closed models run on their maker's own servers (2026-11-18).

Unpinned, OpenRouter sent GPT-6.2 Sol to Amazon Bedrock for 23 of 40 trials, and Bedrock's conversion of the
request turned submit_design's params into "any": the model never saw the format a design has to take. Pinning
picks the host, never what the model reads.
"""
import json
import urllib.request

import pytest

from pbe.runner import agent, llm


def body_posted(model, monkeypatch, **params):
    """The request body llm.chat posts to OpenRouter for this model."""
    posted = []

    def urlopen(request, timeout=None):
        posted.append(request.data)
        raise ConnectionResetError("stop here")
    monkeypatch.setattr(llm, "_key", lambda: "fake")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.LLMError):
        llm.chat(model, [{"role": "user", "content": "u"}], tools=agent.tools(agent.TEST_CONDITION), retries=0, **params)
    return json.loads(posted[0])


@pytest.mark.parametrize("model, hosts", [
    ("openai/gpt-6.2-sol", ["openai"]),
    ("openai/gpt-6.1-sol", ["openai"]),
    ("google/gemini-4-hydrogen", ["google-vertex", "google-ai-studio"]),
    ("google/gemini-4-argon", ["google-vertex", "google-ai-studio"]),
])
def test_a_closed_model_runs_only_on_its_makers_servers(model, hosts, monkeypatch):
    assert body_posted(model, monkeypatch)["provider"] == {"only": hosts, "allow_fallbacks": False}


@pytest.mark.parametrize("model", ["deepseek/deepseek-v4.1-flash", "anthropic/claude-sonnet-5.5"])
def test_other_models_are_left_to_openrouter(model, monkeypatch):
    assert "provider" not in body_posted(model, monkeypatch)


def test_pinning_changes_only_the_provider_field(monkeypatch):
    pinned = body_posted("openai/gpt-6.2-sol", monkeypatch)
    unpinned = body_posted("deepseek/deepseek-v4.1-flash", monkeypatch)
    pinned.pop("provider")
    pinned.pop("model"), unpinned.pop("model")
    assert pinned == unpinned


def test_a_host_comparison_run_sends_every_call_to_the_host_it_names(monkeypatch):
    monkeypatch.setenv("PBE_PROVIDER", "amazon-bedrock")
    for model in ["openai/gpt-6.2-sol", "deepseek/deepseek-v4.1-flash"]:
        assert body_posted(model, monkeypatch)["provider"] == {"only": ["amazon-bedrock"], "allow_fallbacks": False}


def test_a_call_can_still_name_its_own_host(monkeypatch):
    """A probe that compares hosts passes its own provider, which wins over the pin."""
    body = body_posted("openai/gpt-6.2-sol", monkeypatch, provider={"only": ["amazon-bedrock"]})
    assert body["provider"] == {"only": ["amazon-bedrock"]}


def test_leaderboard_runs_send_the_tools_unchanged(monkeypatch):
    monkeypatch.delenv(agent.PARAMS_AS_LIST, raising=False)
    assert agent.sent_tools(agent.TEST_CONDITION) == agent.tools(agent.TEST_CONDITION)


def test_the_list_form_carries_the_same_fields_and_reads_back_as_the_map(monkeypatch):
    monkeypatch.setenv(agent.PARAMS_AS_LIST, "1")
    sent = {t["function"]["name"]: t["function"]["parameters"] for t in agent.sent_tools(agent.TEST_CONDITION)}
    usual = {t["function"]["name"]: t["function"]["parameters"] for t in agent.tools(agent.TEST_CONDITION)}
    for name in ["submit_design", "print_test"]:
        entry = sent[name]["properties"]["params"]["items"]
        mapped = usual[name]["properties"]["params"]["additionalProperties"]
        assert entry["required"] == ["name"] + mapped["required"]
        assert {k: v for k, v in entry["properties"].items() if k != "name"} == mapped["properties"]
    listed = {"params": [{"name": "od", "value": 20, "kind": "design", "source": "design"}], "parts": []}
    assert agent.params_as_map(listed) == {"params": {"od": {"value": 20, "kind": "design", "source": "design"}}, "parts": []}
    assert agent.params_as_map({"params": {"od": {}}}) == {"params": {"od": {}}}
