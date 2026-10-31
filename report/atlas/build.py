"""Build the failure atlas page from the seed files.

Every count on the page comes from seeds/*.yaml; pictures and featured failures
come from report/atlas/examples.yaml. Writes report/atlas/out/ (gitignored,
since the photos are private).

    uv run --with pyyaml python report/atlas/build.py
"""
import html
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

PROJECTS = [
    ("tripod", "Tripod and phone stand", "seeds/tripod-failures.yaml"),
    ("estoa", "Estoa light piece", "seeds/estoa-failures.yaml"),
    ("side", "Lamp mount and organizer", "seeds/side-project-failures.yaml"),
    ("coupons", "The eval's own test coupons", "seeds/coupon-failures.yaml"),
]
STATUS_LABEL = {"failed": "failed", "near-miss": "caught before printing", "unconfirmed": "unconfirmed"}


def load():
    classes = yaml.safe_load((ROOT / "seeds/classes.yaml").read_text())
    seeds = []
    for key, label, path in PROJECTS:
        for s in yaml.safe_load((ROOT / path).read_text()):
            s["project"], s["project_label"] = key, label
            s.setdefault("status", "failed")
            seeds.append(s)
    examples = yaml.safe_load((HERE / "examples.yaml").read_text())
    return classes, seeds, examples


def copy_image(src, name):
    src = Path(src).expanduser()
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".svg":
        dst = OUT / "img" / f"{name}.svg"
        shutil.copy(src, dst)
    else:
        dst = OUT / "img" / f"{name}.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "72", "-Z", "1100",
                        str(src), "--out", str(dst)], check=True, capture_output=True)
    return f"img/{dst.name}"


def esc(s):
    return html.escape(str(s or ""))


def chart(classes, seeds):
    """Stacked horizontal bars: seeds per class by primary class, split by project."""
    counts = {c["id"]: Counter(s["project"] for s in seeds if s["class"] == c["id"]) for c in classes}
    top = max(sum(v.values()) for v in counts.values())
    row_h, label_w, bar_w, pad = 30, 310, 420, 40
    width, height = label_w + bar_w + pad, row_h * len(classes) + 34
    scale = bar_w / top
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Failures per class, by project">']
    for i, c in enumerate(classes):
        y = i * row_h + 4
        num, name = c["id"].split("-", 1)[0], c["name"]
        out.append(f'<a href="#{c["id"]}"><text class="ch-lab" x="0" y="{y + 17}"><tspan class="ch-num">{num}</tspan> {esc(name)}</text></a>')
        x = label_w
        for key, _, _ in PROJECTS:
            n = counts[c["id"]][key]
            if n:
                w = n * scale
                out.append(f'<rect class="bar-{key}" x="{x:.1f}" y="{y + 4}" width="{w - 2:.1f}" height="{row_h - 12}" rx="2"/>')
                x += w
        out.append(f'<text class="ch-val" x="{x + 6:.1f}" y="{y + 17}">{sum(counts[c["id"]].values())}</text>')
    # axis ticks every 2
    ay = len(classes) * row_h + 10
    for t in range(0, top + 1, 2):
        tx = label_w + t * scale
        out.append(f'<line class="ch-tick" x1="{tx:.1f}" y1="4" x2="{tx:.1f}" y2="{ay - 6}"/>')
        out.append(f'<text class="ch-axis" x="{tx:.1f}" y="{ay + 12}" text-anchor="middle">{t}</text>')
    out.append("</svg>")
    return "\n".join(out)


def seed_row(s):
    also = f' <span class="also">also {", ".join(a.split("-", 1)[0] for a in s.get("also", []))}</span>' if s.get("also") else ""
    return (f'<li><span class="sid">{esc(s["id"])}</span> <span class="tag tag-{s["project"]}">{esc(s["project_label"])}</span>'
            f' <span class="st st-{s["status"]}">{esc(STATUS_LABEL[s["status"]])}</span>{also}'
            f'<p>{esc(s["did"])}</p></li>')


def section(c, seeds, ex):
    num = c["id"].split("-", 1)[0]
    mine = [s for s in seeds if s["class"] == c["id"] or c["id"] in s.get("also", [])]
    primary = [s for s in mine if s["class"] == c["id"]]
    by_proj = Counter(s["project"] for s in primary)
    feat = next(s for s in seeds if s["id"] == ex["seed"])
    figs = []
    for i, im in enumerate(ex["images"]):
        src = copy_image(im["path"], f"{num.lower()}-{i}")
        figs.append(f'<figure><img src="{src}" alt="{esc(im["caption"])}" loading="lazy">'
                    f'<figcaption>{esc(im["caption"])} <span class="credit">{esc(im["credit"])}</span></figcaption></figure>')
    proj_chips = " ".join(f'<span class="tag tag-{k}">{esc(l)} {by_proj[k]}</span>' for k, l, _ in PROJECTS if by_proj[k])
    graders = ", ".join(f"<code>{esc(g)}</code>" for g in c["graders"])
    return f"""
<section class="cls" id="{c['id']}">
  <div class="cls-head">
    <span class="cls-num">{num}</span>
    <div>
      <h2>{esc(c['name'])}</h2>
      <p class="cls-desc">{esc(c['description'])}</p>
      <p class="cls-meta"><b>{len(primary)}</b> as the main class{f', {len(mine) - len(primary)} more as a second class' if len(mine) > len(primary) else ''} &middot; {proj_chips}</p>
    </div>
  </div>
  <div class="cls-body">
    <div class="figs">{''.join(figs)}</div>
    <div class="case">
      <p class="eyebrow">Featured failure &middot; {esc(feat['project_label'])}</p>
      <h3>{esc(feat['id'])}</h3>
      <dl>
        <dt>What happened</dt><dd>{esc(feat['did'])}</dd>
        <dt>What was right</dt><dd>{esc(feat['right'])}</dd>
        <dt>How it was found</dt><dd>{esc(feat['found_by'])}</dd>
      </dl>
      <p class="graders">Checked by {graders}</p>
      <details><summary>All {len(mine)} failures in this class</summary><ul class="seeds">{''.join(seed_row(s) for s in mine)}</ul></details>
    </div>
  </div>
</section>"""


def page(classes, seeds, examples):
    total = len(seeds)
    failed = sum(s["status"] == "failed" for s in seeds)
    near = sum(s["status"] == "near-miss" for s in seeds)
    c1 = sum(s["class"] == "C1-unmeasured" for s in seeds)
    legend = " ".join(f'<span class="lg"><i class="sw bar-{k}"></i>{esc(l)}</span>' for k, l, _ in PROJECTS)
    sections = "\n".join(section(c, seeds, examples[c["id"]]) for c in classes)
    return f"""<title>Print Failure Atlas</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a field guide. One section per failure class: the picture of the real failure beside the case file. */
:root {{
  --bg: #f3f4f1; --panel: #ffffff; --fg: #1a211e; --muted: #5b6661; --rule: #d5dad6;
  --accent: #c2410c; --tripod: #2f6f8f; --estoa: #b7791f; --side: #6b8f3a;
  --ok: #2f7a4f; --warn: #a15c07;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #121614; --panel: #1a201d; --fg: #e4e9e6; --muted: #9aa49f; --rule: #2e3632;
  --accent: #f08a4b; --tripod: #6fb0d0; --estoa: #e0aa52; --side: #9cc46a; --ok: #6cc391; --warn: #e3a54a; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #121614; --panel: #1a201d; --fg: #e4e9e6; --muted: #9aa49f; --rule: #2e3632;
  --accent: #f08a4b; --tripod: #6fb0d0; --estoa: #e0aa52; --side: #9cc46a; --ok: #6cc391; --warn: #e3a54a; color-scheme: dark; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.55 var(--body); }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 40px 80px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
h1, h2, h3 {{ font-family: var(--display); font-weight: 700; letter-spacing: .01em; text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(40px, 7vw, 64px); line-height: 1; }}
.kicker {{ font: 500 12px/1 var(--mono); text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin: 0 0 14px; }}
.lede {{ max-width: 62ch; font-size: 17px; margin: 18px 0 0; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 28px; margin: 28px 0 0; padding: 0; list-style: none; }}
.stats b {{ display: block; font: 700 40px/1 var(--display); font-variant-numeric: tabular-nums; }}
.stats span {{ color: var(--muted); font-size: 13px; }}
.chart {{ margin: 36px 0 8px; padding: 20px; background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; overflow-x: auto; }}
.chart svg {{ width: 100%; min-width: 560px; height: auto; display: block; }}
.ch-lab {{ font: 14px var(--body); fill: var(--fg); }}
.ch-num {{ font: 500 12px var(--mono); fill: var(--muted); }}
.ch-val {{ font: 600 13px var(--mono); fill: var(--fg); }}
.ch-axis {{ font: 11px var(--mono); fill: var(--muted); }}
.ch-tick {{ stroke: var(--rule); stroke-width: 1; }}
.chart a:hover .ch-lab {{ fill: var(--accent); }}
.bar-tripod {{ fill: var(--tripod); background: var(--tripod); }} .bar-estoa {{ fill: var(--estoa); background: var(--estoa); }} .bar-side {{ fill: var(--side); background: var(--side); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); }}
.lg {{ display: inline-flex; align-items: center; gap: 6px; }} .sw {{ width: 12px; height: 12px; border-radius: 2px; display: inline-block; }}
.note {{ color: var(--muted); font-size: 13px; max-width: 70ch; }}
.cls {{ border-top: 2px solid var(--fg); margin-top: 64px; padding-top: 22px; scroll-margin-top: 16px; }}
.cls-head {{ display: grid; grid-template-columns: auto 1fr; gap: 18px; align-items: start; }}
.cls-num {{ font: 700 44px/0.9 var(--display); color: var(--accent); min-width: 2.2ch; }}
h2 {{ font-size: 32px; line-height: 1.05; }}
.cls-desc {{ margin: 6px 0 0; max-width: 70ch; }}
.cls-meta {{ margin: 10px 0 0; color: var(--muted); font-size: 13px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.cls-meta b {{ color: var(--fg); }}
.cls-body {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 28px; margin-top: 22px; }}
@media (max-width: 760px) {{ .cls-body {{ grid-template-columns: 1fr; }} .cls-head {{ grid-template-columns: 1fr; gap: 4px; }} }}
.figs {{ display: grid; gap: 16px; min-width: 0; }}
figure {{ margin: 0; }}
figure img {{ width: 100%; max-height: 520px; object-fit: contain; background: var(--panel); border: 1px solid var(--rule); border-radius: 4px; display: block; }}
figcaption {{ font-size: 13px; color: var(--muted); margin-top: 8px; }}
.credit {{ font: 11px var(--mono); text-transform: uppercase; letter-spacing: .06em; margin-left: 4px; }}
.case {{ min-width: 0; }}
.eyebrow {{ font: 500 11px/1 var(--mono); text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin: 0 0 8px; }}
h3 {{ font: 500 18px/1.2 var(--mono); letter-spacing: 0; }}
dl {{ margin: 14px 0 0; display: grid; gap: 4px 0; }}
dt {{ font: 600 12px var(--body); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-top: 10px; }}
dd {{ margin: 0; }}
.graders {{ font-size: 13px; color: var(--muted); margin: 16px 0 0; }}
code {{ font: 12.5px var(--mono); background: var(--panel); border: 1px solid var(--rule); padding: 1px 5px; border-radius: 3px; color: var(--fg); overflow-wrap: anywhere; }}
details {{ margin-top: 16px; border-top: 1px solid var(--rule); padding-top: 10px; }}
summary {{ cursor: pointer; font-weight: 600; font-size: 14px; }}
summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.seeds {{ list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 12px; }}
.seeds p {{ margin: 4px 0 0; font-size: 13.5px; }}
.sid {{ font: 500 13px var(--mono); }}
.tag {{ font-size: 11.5px; padding: 1px 7px; border-radius: 10px; border: 1px solid currentColor; white-space: nowrap; }}
.tag-tripod {{ color: var(--tripod); }} .tag-estoa {{ color: var(--estoa); }} .tag-side {{ color: var(--side); }}
.st {{ font-size: 11.5px; color: var(--muted); }} .st-failed {{ color: var(--accent); }} .st-near-miss {{ color: var(--warn); }}
.also {{ font: 11px var(--mono); color: var(--muted); }}
footer {{ margin-top: 72px; border-top: 1px solid var(--rule); padding-top: 18px; color: var(--muted); font-size: 13px; max-width: 75ch; }}
a {{ color: inherit; }}
@media (prefers-reduced-motion: no-preference) {{ html {{ scroll-behavior: smooth; }} }}
</style>
<div class="wrap">
<header>
  <p class="kicker">Print-and-Build Eval &middot; failure classes</p>
  <h1>Print Failure Atlas</h1>
  <p class="lede">Every failure here happened for real, while Dan designed and built printed objects with an AI agent: a tripod mount and phone stand, the Estoa light piece, and two smaller projects. Each was traced to the transcript and grouped into a class that doesn't depend on the object. Each class becomes a check the eval runs on any design.</p>
  <ul class="stats">
    <li><b>{total}</b><span>real failures</span></li>
    <li><b>{failed}</b><span>went wrong physically</span></li>
    <li><b>{near}</b><span>caught before printing</span></li>
    <li><b>{c1}</b><span>were guessed dimensions, the top class</span></li>
  </ul>
</header>
<div class="chart">
  {chart(classes, seeds)}
  <div class="legend" style="margin-top:10px">{legend}</div>
</div>
<p class="note">Counted by each failure's main class; some also belong to a second. Electronics and power failures from Estoa were recorded but are outside this eval and not shown.</p>
{sections}
<footer>Built from <code>seeds/*.yaml</code> and <code>seeds/classes.yaml</code> by <code>report/atlas/build.py</code>. Each failure links to the agent session and timestamp it came from. Photos are Dan's.</footer>
</div>
"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    classes, seeds, examples = load()
    (OUT / "index.html").write_text(page(classes, seeds, examples))
    print(f"wrote {OUT / 'index.html'}: {len(seeds)} seeds, {len(list((OUT / 'img').iterdir()))} images")


if __name__ == "__main__":
    main()
