"""The host comparison chart: the same model on the same task, sent to OpenAI's servers or to Amazon Bedrock's through
OpenRouter, with how often it asked for a test print and how often its design passed. No model calls.

    uv run python scripts/host_figures.py

Reads GPT-6.2 Sol's saved M3 knob trials (Test prints first) from the runs below and writes
docs/media/host-comparison.svg: one box for what every trial shares (model, prompt, task) forking into one card per
host, each with its counts in large type and one square per trial under them (filled when the trial asked for a test
print, check-marked when its design passed). Bedrock's card pools every setting tried there. Dan picked cards with
squares from five sketches after a Decisions-model poll, then asked for the fork (2026-11-18).
"""
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
OUT = ROOT / "docs/media/host-comparison.svg"
MODEL_FOLDER = "openai__gpt-6.2-sol"
TASK = "nut-knob/M3"
TITLE = "Same model. Different server."

# (host, runs): every call in each run went to the host named; the trials record it. Bedrock's row is the planned
# 10-trial run as sent; the other settings tried there (tools as a list, reasoning asked for) are in the change file
HOSTS = [
    ("on OpenAI server", ["smoke-new-models"]),
    ("on Amazon Bedrock server", ["host-bedrock"]),
]


@dataclass
class Trial:
    asked: bool  # asked for at least one test print
    passed: bool


@dataclass
class Host:
    name: str
    trials: list[Trial]
    served_by: set

    @property
    def asked(self):
        return sum(trial.asked for trial in self.trials)

    @property
    def passed(self):
        return sum(trial.passed for trial in self.trials)


def read_host(name: str, runs: list[str]) -> Host:
    grades = [json.loads(path.read_text()) for run in runs
              for path in sorted((RUNS / run / TASK / "can_test" / MODEL_FOLDER).glob("t*/grades.json"))]
    trials = [Trial(bool(g.get("test_prints")), bool(g["all_pass"])) for g in grades]
    return Host(name, trials, {call.get("provider") for g in grades for call in g["calls"]})


STYLE = ("<style>text{fill:#26302c}.title{font-weight:800;font-size:34px}.sub{font-size:17px;fill:#4a5450}"
         ".name{font-weight:700;font-size:20px}.stage{font-size:14px;fill:#4a5450}.count{font-weight:800;font-size:20px}"
         ".on{fill:#fff}.off{fill:#8a938f}.muted{fill:#6b7570;font-size:13px}"
         ".s0{fill:#9fb3c2}.s1{fill:#2f6f9f}.s2{fill:#b35c1e}.empty{fill:none;stroke:#c3cac6;stroke-width:1.5;stroke-dasharray:5 4}"
         "@media (prefers-color-scheme: dark){text{fill:#e4e9e6}.sub,.stage{fill:#b9c1bd}.muted{fill:#9aa39f}.off{fill:#7d8782}"
         ".s0{fill:#4d6272}.s1{fill:#4f8fbf}.s2{fill:#d9783a}.empty{stroke:#4a534f}}</style>")

# the funnel's stages: label, how many trials reached it
STAGES = [("Trials", lambda host: len(host.trials)),
          ("Asked for a test print first", lambda host: host.asked),
          ("Design passed", lambda host: host.passed)]


def funnel(host: Host, cx: float, top: float, full: float, bar_h: float, step: float) -> list[str]:
    """Three stacked bars centered on cx, each as wide as the share of trials that reached that stage; a stage no trial
    reached is a dashed outline at full width, so it reads as empty rather than missing."""
    out = [f'<text class="name" x="{cx}" y="{top - 40}" text-anchor="middle">GPT-6.2 Sol</text>',
           f'<text class="name" x="{cx}" y="{top - 16}" text-anchor="middle">{host.name}</text>']
    for i, (_, reached) in enumerate(STAGES):
        n, y = reached(host), top + i * step
        if n == 0:
            out.append(f'<rect class="empty" x="{cx - full / 2}" y="{y}" width="{full}" height="{bar_h}" rx="6"/>')
            out.append(f'<text class="count off" x="{cx}" y="{y + bar_h / 2 + 7}" text-anchor="middle">0</text>')
            continue
        w = full * n / len(host.trials)
        out.append(f'<rect class="s{i}" x="{cx - w / 2:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="6"/>')
        out.append(f'<text class="count on" x="{cx}" y="{y + bar_h / 2 + 7}" text-anchor="middle">{n}</text>')
    return out


def chart(hosts: list[Host]) -> str:
    width, left, labels_w, full, bar_h, step = 830, 40, 200, 230, 48, 64
    top = 214
    height = top + step * len(STAGES) + 40
    centers = [left + labels_w + full / 2 + i * (full + 40) for i in range(len(hosts))]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
           'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">', STYLE,
           f'<text class="title" x="{left}" y="60">{TITLE}</text>',
           f'<text class="sub" x="{left}" y="92">GPT-6.2 Sol, same prompt, same 3D-print task, through OpenRouter.</text>',
           f'<text class="sub" x="{left}" y="116">On Amazon Bedrock it never asked for a test print, and nothing passed.</text>']
    for i, (label, _) in enumerate(STAGES):
        out.append(f'<text class="stage" x="{left}" y="{top + i * step + bar_h / 2 + 5}">{label}</text>')
    for host, cx in zip(hosts, centers):
        out += funnel(host, cx, top, full, bar_h, step)
    out.append(f'<text class="muted" x="{left}" y="{height - 14}">10 trials on each server: a knob with an M3 nut pocket, '
               'test prints allowed.</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    hosts = [read_host(name, runs) for name, runs in HOSTS]
    for host in hosts:
        print(f"{host.name}: {host.asked}/{len(host.trials)} asked, {host.passed}/{len(host.trials)} passed, "
              f"served by {sorted(map(str, host.served_by))}")
    OUT.write_text(chart(hosts))
    print(OUT)


if __name__ == "__main__":
    main()
