"""Confirm prompt caching works through OpenRouter (issue 34): send one task's opening request twice
and save both calls' usage. Caching works if the second call reads tokens from the cache.

    uv run python scripts/caching_check.py --model anthropic/claude-haiku-5.5

Costs a few cents. Saves results/caching-check/<model>.json, stamped with the code version.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from pbe import eval as runner
from pbe.runner import agent, llm, tasks
from pbe.runner.measure import Person
from pbe.runner.trial_record import ModelCall

OUT = runner.ROOT / "results/caching-check"
TASK = "m5-spacer"
MAX_TOKENS = 300  # the reply doesn't matter; only the prompt is cached


class CachingCheck(BaseModel):
    model: str
    task: str
    caching_requested: bool
    calls: list[ModelCall]
    cache_works: bool  # the second call read tokens from the cache
    date: str
    commit: str


def opening_request(task_id):
    task = tasks.load(task_id)
    max_turns = agent.DEFAULT_MAX_TURNS["can_ask"]
    return agent.opening_messages(task, "can_ask", Person(task.hidden_facts), max_turns), agent.tools("can_ask")


def call_once(model, messages, tools) -> ModelCall:
    response = llm.chat(model, messages, tools=tools, max_tokens=MAX_TOKENS, **llm.caching_params(model))
    return ModelCall.from_reply(llm.Reply.model_validate(response))


def check(model) -> CachingCheck:
    messages, tools = opening_request(TASK)
    calls = [call_once(model, messages, tools) for _ in range(2)]
    return CachingCheck(model=model, task=TASK, caching_requested=llm.requests_caching(model), calls=calls,
                        cache_works=calls[1].cached_tokens > 0,
                        date=datetime.now(timezone.utc).isoformat(timespec="seconds"), commit=runner.code_version())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    result = check(args.model)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.model.replace('/', '__')}.json"
    path.write_text(json.dumps(result.model_dump(), indent=1))
    for number, call in enumerate(result.calls, 1):
        print(f"call {number}: {call.provider}, prompt {call.prompt_tokens}, cached {call.cached_tokens}, "
              f"written {call.cache_write_tokens}, ${call.cost_usd:.5f}")
    print(f"cache works: {result.cache_works}; saved {path.relative_to(runner.ROOT)}")


if __name__ == "__main__":
    main()
