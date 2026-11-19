"""The image for the post about OpenRouter's host choice: GPT-6.2 Sol on OpenAI's server against Amazon Bedrock's, each
as a pipeline (reasoning, test prints, first submission, result) with a small chart of every trial. No model calls.

    uv run python scripts/host_post_image.py

Reads GPT-6.2 Sol's saved M3 knob trials (Test prints first) from the two runs below and writes docs/media/host-post.png
(3200x1800, for X). The layout is Gemini 4 Argon's (asked through OpenRouter on 2026-11-18 for designs from the post and
the facts; Dan picked this one after a Decisions-model poll), with its typed-in numbers replaced by the saved runs and its
wording held to what the records show.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
OUT = ROOT / "docs/media/host-post.png"
TRIALS = "nut-knob/M3/can_test/openai__gpt-6.2-sol"
OPENAI_RUN, BEDROCK_RUN = "smoke-new-models", "host-bedrock"  # every call in each went to that host; the trials record it
REJECTED = "isn't a valid submission"  # the runner's reply to a submission it sends back

C = dict(bg="#F8FAFC", dark="#0F172A", muted="#475569", border="#CBD5E1", oai_bg="#F0F7FF", oai="#2563EB",
         green="#059669", bed_bg="#FFF1F2", bed="#E11D48", red="#BE123C", ungraded="#94A3B8")


@dataclass
class Trial:
    number: int
    reasoning: int  # reasoning tokens over the trial's calls
    prints: int  # test prints asked for
    rejected_first: bool  # its first design submission was sent back as malformed
    result: str  # "P" passed, "F" failed, "NG" not graded


def read_trials(run: str) -> list[Trial]:
    trials = []
    for path in (RUNS / run / TRIALS).glob("t*/grades.json"):
        grades = json.loads(path.read_text())
        transcript = json.loads((path.parent / "transcript.json").read_text())
        findings = grades["findings"]
        result = "P" if grades["all_pass"] else "F" if any(f.get("ok") is False for f in findings) else "NG"
        trials.append(Trial(grades["trial"],
                            sum((c["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for c in grades["calls"]),
                            len(grades.get("test_prints") or []),
                            any(m.get("role") == "tool" and REJECTED in str(m.get("content")) for m in transcript),
                            result))
    return sorted(trials, key=lambda trial: trial.number)


def box(ax, xy, w, h, face, edge, lw=1.5, pad=0.3, r=1.2):
    ax.add_patch(mpatches.FancyBboxPatch(xy, w, h, boxstyle=f"round,pad={pad},rounding_size={r}", facecolor=face, edgecolor=edge, linewidth=lw))


def arrow(ax, x0, x1, y, color, dashed=False):
    ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="->,head_width=0.35,head_length=0.45", lw=2.2,
                                                                 ls="--" if dashed else "-", color=color))


def result_dots(ax, trials, y_top, pass_color):
    for i, trial in enumerate(trials):
        color = {"P": pass_color, "F": C["red"]}.get(trial.result, C["ungraded"])
        ax.scatter(134.3 + (i % 5) * 3.2, y_top - (i // 5) * 3.0, s=110, color=color, edgecolors="#FFFFFF", lw=1, zorder=3)


def counts(trials):
    return {kind: sum(t.result == kind for t in trials) for kind in ("P", "F", "NG")}


def draw(openai: list[Trial], bedrock: list[Trial]) -> plt.Figure:
    n_o, n_b = len(openai), len(bedrock)
    fig, ax = plt.subplots(figsize=(16, 9), dpi=200)
    fig.patch.set_facecolor(C["bg"])
    ax.set_facecolor(C["bg"]); ax.set_xlim(0, 160); ax.set_ylim(0, 90); ax.axis("off")

    ax.text(5, 84, "OpenRouter Server Routing Changes Model Behavior", fontsize=22, fontweight="bold", color=C["dark"])
    ax.text(5, 79.5, f"Same model (GPT-6.2 Sol) & same prompt across {n_o} trials per server: designing a 3D-printed M3 knob",
            fontsize=13, color=C["muted"])

    # shared input, with OpenRouter choosing the server
    box(ax, (5, 13), 26, 61, "#FFFFFF", "#64748B", lw=2, pad=0.4, r=2)
    ax.text(18, 69.5, "SHARED INPUT", fontsize=11, fontweight="bold", color=C["muted"], ha="center")
    ax.plot([7.5, 28.5], [67, 67], color=C["border"], lw=1.5)
    ax.text(18, 63, "Model", fontsize=9.5, color=C["muted"], ha="center")
    ax.text(18, 59.5, "GPT-6.2 Sol", fontsize=14, fontweight="bold", color=C["dark"], ha="center")
    ax.text(18, 53.5, f"Eval Task ({n_o} Trials)", fontsize=9.5, color=C["muted"], ha="center")
    ax.text(18, 49, "3D-Printed Knob\n(M3 Nut Pocket)", fontsize=11.5, fontweight="bold", color=C["dark"], ha="center", linespacing=1.25)
    theta = np.linspace(0, 2 * np.pi, 7)
    ax.fill(18 + 3.6 * np.cos(theta), 41 + 3.6 * np.sin(theta), facecolor="#E2E8F0", edgecolor="#334155", lw=1.8)
    ax.fill(18 + 1.7 * np.cos(theta), 41 + 1.7 * np.sin(theta), facecolor="#FFFFFF", edgecolor=C["oai"], lw=1.5)
    box(ax, (7, 15.5), 22, 18.5, "#F1F5F9", "#475569", r=1.5)
    ax.text(18, 30.5, "OpenRouter", fontsize=12, fontweight="bold", color=C["dark"], ha="center")
    ax.text(18, 27, "chooses the server\nthat runs the model", fontsize=9.5, color=C["muted"], ha="center", linespacing=1.2)
    ax.text(18, 21.5, "• Pinned to OpenAI", fontsize=9.5, fontweight="bold", color=C["oai"], ha="center")
    ax.text(18, 18, "• Unpinned: can route\n  to Bedrock", fontsize=9, fontweight="bold", color=C["bed"], ha="center", linespacing=1.15)
    ax.annotate("", xy=(38.5, 59), xytext=(31.5, 28), arrowprops=dict(arrowstyle="->,head_width=0.5,head_length=0.6", lw=3,
                                                                        color=C["oai"], connectionstyle="arc3,rad=-0.18"))
    ax.annotate("", xy=(38.5, 26), xytext=(31.5, 22), arrowprops=dict(arrowstyle="->,head_width=0.5,head_length=0.6", lw=3,
                                                                        color=C["bed"], connectionstyle="arc3,rad=0.12"))

    # OpenAI lane
    box(ax, (39.5, 45.5), 115.5, 29, C["oai_bg"], C["oai"], lw=2, pad=0.4, r=2)
    box(ax, (42, 70), 44, 4, C["oai"], "none", pad=0.2, r=1)
    ax.text(64, 72, "GPT-6.2 Sol on OpenAI server", fontsize=12, fontweight="bold", color="#FFFFFF", ha="center", va="center")
    reasoning = [t.reasoning for t in openai]
    box(ax, (42, 47.5), 26, 20.5, "#FFFFFF", "#93C5FD")
    ax.text(55, 65, "1. REASONING", fontsize=9.5, fontweight="bold", color=C["oai"], ha="center")
    ax.text(55, 60.8, f"{min(reasoning):,}–{max(reasoning):,} tokens", fontsize=12.5, fontweight="bold", color=C["dark"], ha="center")
    ax.text(55, 57.5, f"{round(mean(reasoning)):,} avg across {n_o} trials", fontsize=8.8, color=C["muted"], ha="center")
    for i, tokens in enumerate(reasoning):
        ax.add_patch(mpatches.Rectangle((44.2 + i * 2.25, 49), 1.6, tokens / max(reasoning) * 6.2, facecolor=C["oai"], alpha=0.85))
    ax.plot([43.8, 66.2], [49, 49], color=C["border"], lw=1)
    arrow(ax, 68.3, 71.5, 57.5, C["oai"])
    asked = sum(t.prints > 0 for t in openai)
    box(ax, (72, 47.5), 26, 20.5, "#FFFFFF", "#93C5FD")
    ax.text(85, 65, "2. TEST PRINTS", fontsize=9.5, fontweight="bold", color=C["oai"], ha="center")
    ax.text(85, 60.8, f"{asked} / {n_o} asked", fontsize=13.5, fontweight="bold", color=C["dark"], ha="center")
    ax.text(85, 57.3, f"{sum(t.prints for t in openai)} test prints in all", fontsize=9, fontweight="bold", color=C["green"], ha="center")
    ax.text(85, 55.2, "per trial:", fontsize=8, color=C["muted"], ha="center")
    for i, trial in enumerate(openai):
        for k in range(trial.prints):
            ax.add_patch(mpatches.Rectangle((74.2 + i * 2.25, 49.2 + k * 2.8), 1.6, 2.3, facecolor=C["green"]))
    arrow(ax, 98.3, 101.5, 57.5, C["oai"])
    rejected = sum(t.rejected_first for t in openai)
    box(ax, (102, 47.5), 23, 20.5, "#FFFFFF", "#93C5FD")
    ax.text(113.5, 65, "3. 1ST SUBMISSION", fontsize=9.5, fontweight="bold", color=C["oai"], ha="center")
    ax.text(113.5, 59.5, f"{rejected} / {n_o} Rejected", fontsize=13, fontweight="bold", color=C["dark"], ha="center")
    ax.text(113.5, 53.5, "the tool's format\narrived intact", fontsize=9, color=C["muted"], ha="center", linespacing=1.25)
    arrow(ax, 125.3, 128.5, 57.5, C["green"])
    c = counts(openai)
    box(ax, (129, 47.5), 23.5, 20.5, "#ECFDF5", C["green"], lw=2)
    ax.text(140.75, 65, "4. EVAL RESULT", fontsize=9.5, fontweight="bold", color=C["green"], ha="center")
    ax.text(140.75, 60.5, f"{c['P']} / {n_o} Passed", fontsize=14.5, fontweight="bold", color=C["green"], ha="center")
    ax.text(140.75, 56.8, f"{c['NG']} not graded • {c['F']} failed", fontsize=8.8, fontweight="bold", color=C["muted"], ha="center")
    result_dots(ax, openai, 53.2, C["green"])

    # Bedrock lane
    box(ax, (39.5, 11), 115.5, 29, C["bed_bg"], C["bed"], lw=2, pad=0.4, r=2)
    box(ax, (42, 35.5), 53, 4, C["bed"], "none", pad=0.2, r=1)
    ax.text(68.5, 37.5, "GPT-6.2 Sol on Amazon Bedrock server", fontsize=12, fontweight="bold", color="#FFFFFF", ha="center", va="center")
    zeros = sum(t.reasoning == 0 for t in bedrock)
    box(ax, (42, 13), 26, 20.5, "#FFFFFF", "#FDA4AF")
    ax.text(55, 30.5, "1. REASONING", fontsize=9.5, fontweight="bold", color=C["bed"], ha="center")
    ax.text(55, 26.2, f"0 tokens ({zeros}/{n_b})", fontsize=12.5, fontweight="bold", color=C["red"], ha="center")
    ax.text(55, 22.8, "Trials: " + ", ".join(str(t.reasoning) for t in bedrock), fontsize=8.3, color=C["muted"], ha="center")
    ax.text(55, 16.8, "Asking for medium or high\nreasoning didn't change it", fontsize=8.3, fontweight="bold", color=C["red"], ha="center", linespacing=1.2)
    arrow(ax, 68.3, 71.5, 23, C["bed"], dashed=True)
    box(ax, (72, 13), 26, 20.5, "#FFFFFF", "#FDA4AF")
    ax.text(85, 30.5, "2. TEST PRINTS", fontsize=9.5, fontweight="bold", color=C["bed"], ha="center")
    ax.text(85, 25.2, f"{sum(t.prints > 0 for t in bedrock)} / {n_b} asked", fontsize=13.5, fontweight="bold", color=C["red"], ha="center")
    ax.text(85, 18.8, f"{sum(t.prints for t in bedrock)} test prints across all\n{n_b} trials (never asked)", fontsize=9, color=C["muted"], ha="center", linespacing=1.25)
    arrow(ax, 98.3, 101.5, 23, C["bed"], dashed=True)
    box(ax, (102, 13), 23, 20.5, "#FFFFFF", "#FDA4AF")
    ax.text(113.5, 30.5, "3. 1ST SUBMISSION", fontsize=9.5, fontweight="bold", color=C["bed"], ha="center")
    ax.text(113.5, 25.5, f"{sum(t.rejected_first for t in bedrock)} / {n_b} Rejected", fontsize=12.5, fontweight="bold", color=C["red"], ha="center")
    ax.text(113.5, 18.5, "as malformed: Bedrock's\nconversion dropped the\ntool's format", fontsize=8.5, color=C["muted"], ha="center", linespacing=1.2)
    arrow(ax, 125.3, 128.5, 23, C["red"])
    c = counts(bedrock)
    box(ax, (129, 13), 23.5, 20.5, "#FFE4E6", C["red"], lw=2)
    ax.text(140.75, 30.5, "4. EVAL RESULT", fontsize=9.5, fontweight="bold", color=C["red"], ha="center")
    ax.text(140.75, 26, f"{c['P']} / {n_b} Passed", fontsize=14.5, fontweight="bold", color=C["red"], ha="center")
    ax.text(140.75, 22.3, f"{c['F']} failed • {c['NG']} not graded", fontsize=8.8, fontweight="bold", color=C["muted"], ha="center")
    result_dots(ax, bedrock, 18.7, C["green"])

    # legend, then the takeaway on its own line
    for x, color, label, weight in [(6, C["green"], "Passed", C["dark"]), (17, C["ungraded"], "Not graded (records couldn't decide the fit)", C["muted"]),
                                    (60, C["red"], "Failed", C["dark"])]:
        ax.scatter(x, 6.2, s=90, color=color)
        ax.text(x + 1.5, 6.2, label, fontsize=10, fontweight="bold", color=weight, va="center")
    ax.text(5, 2.4, "Asking for a cheap test print before committing is what makes the model succeed.", fontsize=10,
            fontweight="bold", color=C["dark"], va="center")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    return fig


def main():
    openai, bedrock = read_trials(OPENAI_RUN), read_trials(BEDROCK_RUN)
    fig = draw(openai, bedrock)
    fig.savefig(OUT, dpi=200, facecolor=C["bg"])
    print(OUT)


if __name__ == "__main__":
    main()
