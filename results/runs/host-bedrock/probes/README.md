# Host probes, 2026-11-18

Three one-off calls to GPT-6.2 Sol through OpenRouter, each pinned to one host (`provider.only`, no fallbacks), run from
these scripts with `uv run python results/runs/host-bedrock/probes/<script>.py` at the commit that adds this folder. Each
sends `agent.tools("can_test")`, the tools a Test prints first trial gets. The outputs below are copied from the terminal
as they ran; the scripts saved nothing else. Total cost: under $0.04.

## tool_format.py: can the model see submit_design's format?

Asked, without calling a tool, to list its tools and the fields each `params` entry requires. Two calls per host.

| Host | Prompt tokens | What the model said `params` entries need |
|---|---|---|
| OpenAI | 1,641 | `value`, `kind` and `source`; `kind` is `hardware`, `world` or `design` |
| Amazon Bedrock | 1,098 | "submit_design defines `params` as `any`. Required fields for each entry: not given." |

Both hosts listed all four tools (`measure`, `submit_design`, `report_limitation`, `print_test`).

## tool_shape.py: is it the shape of `params`?

`params` is a map from names the model chooses to entries, written as `additionalProperties`. The same tools with
`params` rewritten as a list of entries with fixed fields (`name` plus the same fields) were sent to each host.

| What was sent | Host | Prompt tokens | What the model said |
|---|---|---|---|
| params as a map (as in every trial) | Amazon Bedrock | 1,083 | "`params` is required and typed as `any`. Its structure is not given." |
| params as a map | OpenAI | 1,626 | every field, with `kind`'s three values and `source`'s seven |
| params as a list | Amazon Bedrock | 1,444 | every field, with `kind`'s three values and `source`'s seven |
| params as a list | OpenAI | 1,645 | every field, with `kind`'s three values and `source`'s seven |

## reasoning.py: does Bedrock reason when asked?

One short question about a nut pocket's size, at each reasoning effort.

| Host | Effort asked for | Reasoning tokens | Output tokens |
|---|---|---|---|
| OpenAI | none | 0 | 66 |
| OpenAI | medium | 0 | 69 |
| OpenAI | high | 74 | 142 |
| Amazon Bedrock | none | 0 | 66 |
| Amazon Bedrock | medium | 0 | 59 |
| Amazon Bedrock | high | 0 | 55 |
