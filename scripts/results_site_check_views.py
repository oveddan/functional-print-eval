"""The drawings on the results site's "How the checks work" page: for each example in scripts/results_site_checks.yaml,
passing, failing or not graded, the same kind of drawing scripts/results_site_views.py makes for a failing check, drawn
from today's code. No model calls.

    uv run python scripts/results_site_check_views.py              # draw, upload, write the committed manifest
    uv run python scripts/results_site_check_views.py --no-upload  # draw only

Every example is drawn here, not taken from scripts/results_site_views.json, so a grader change is redrawn with the
page. Each drawing calls the views script's own drawers, which call the grader's own functions; for bridges and
connected_bodies on a passing part (whose drawers look only for a failure) and for Estoa's R6 (whose drawer predates the
common-fastener rule) it has its own, on the views script's helpers and the grader's functions. The images carry no
caption: the page prints the finding beside them, and the caption becomes the image's alt text. Parts are built into
each design's parts/ folder as the views script builds them. Figures go to results/local/site-check-views/objects/
<sha256-8>/<name>.webp (git-ignored) and up to the media host with the media script's uploader (at most 6 at a time);
the committed manifest, scripts/results_site_check_views.json, holds URLs only and is what scripts/results_site.py reads.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import results_site  # noqa: E402  check titles, reader wording
import results_site_media as media  # noqa: E402  the uploader and the media host's URLs
import results_site_views as views  # noqa: E402  the drawers and drawing helpers

from shapely.geometry import LineString, Point  # noqa: E402

from pbe.parts.printer import printer  # noqa: E402

ROOT = media.ROOT
EXPLAINED = Path(__file__).with_name("results_site_checks.yaml")
COMMITTED = Path(__file__).with_name("results_site_check_views.json")
WORK = ROOT / "results/local/site-check-views"
OBJECTS = WORK / "objects"
LEDGER = WORK / "uploaded.txt"
VERSION = 2


def all_examples() -> list[dict]:
    """[{check, family, trial, part, outcome}] for every example on the page."""
    found = []
    for entry in yaml.safe_load(EXPLAINED.read_text())["checks"]:
        for example in entry.get("examples") or []:
            if entry["check"] == "builds":
                continue  # code that didn't run has no shape to draw
            found.append({"check": entry["check"], "family": entry["task"], "trial": example["trial"],
                          "part": example.get("part", "-"), "outcome": example["outcome"]})
    return found


def saved_finding(folder: Path, check: str, part: str) -> dict:
    findings, _ = media.saved_findings(folder)
    for finding in findings:
        if finding["check"] == check and (finding.get("part") or "-") == part and not finding.get("test_print"):
            return finding
    raise SystemExit(f"{folder.relative_to(media.RUNS)}: no saved {check} finding on part {part}")


# ---- the two checks whose drawers look only for a failure ----

def pass_bridges(design, finding, part_id):
    """The widest overhang on the part that the bridge check assessed and passed, drawn as view_bridges draws a failing
    one: the layer, the layer below and the strands in the best direction, each green if it lands on plastic at both ends."""
    mesh = design.mesh(part_id)
    assessed = [overhang for overhang in views.cached_overhangs(mesh) if overhang.ok]
    if not assessed:
        raise views.NoView("no overhang on this part needed a bridge, so there's no roof to draw")
    first = max(assessed, key=lambda overhang: overhang.region.area)
    layer_h = printer().layer_mm
    shifted = mesh.copy()
    shifted.apply_translation([0, 0, -mesh.bounds[0][2]])
    this_layer = views.bridges._layer_at(shifted, first.z + layer_h / 2)
    fig, (whole, zoom, side) = views.new_figure("two+strip")
    for target in (whole, zoom):
        views.fill(target, this_layer, fc=views.LIGHT, ec=views.EDGE, lw=0.5)
        views.fill(target, first.support, z=2, fc=views.PART, ec=views.EDGE, lw=0.5)
        views.fill(target, first.region, z=3, fc="#cfe8d8", ec=views.OK, lw=0.9)
    for line, anchored in first.strands:
        xs, ys = line.xy
        zoom.plot(xs, ys, color=views.OK if anchored else views.FAIL, lw=0.6, zorder=4)
    x0, y0, x1, y1 = first.region.bounds
    pad = max(4.0, 0.35 * max(x1 - x0, y1 - y0))
    views.frame(whole, views.bounds_of(this_layer, first.support))
    views.frame(zoom, (x0 - pad, y0 - pad, x1 + pad, y1 + pad), pad=0)
    whole.set_title(f"Layer at z = {first.z:.1f} mm, from above")
    zoom.set_title(f"Zoomed: strands at {first.best_angle}°")
    probe = first.region.representative_point()
    across = views._across_the_roof(first.region)
    cut = views.plane_cut([shifted], (probe.x, probe.y, 0), (across[0], across[1], 0), (0, 0, 1))
    views.fill(side, cut, fc=views.PART, ec=views.EDGE, lw=0.5)
    reach = max(x1 - x0, y1 - y0) + 2
    line = LineString([(probe.x - across[0] * reach, probe.y - across[1] * reach), (probe.x + across[0] * reach, probe.y + across[1] * reach)])
    span = first.region.intersection(line)
    for piece in getattr(span, "geoms", [span]):
        if piece.geom_type == "LineString" and not piece.is_empty:
            along = [(x - probe.x) * across[0] + (y - probe.y) * across[1] for x, y in piece.coords]
            side.plot(along, [first.z + layer_h] * len(along), color=views.OK, lw=3, solid_capstyle="butt", zorder=5)
    views.frame(side, views.bounds_of(cut, Point(0, first.z)), bottom_room=0.2)
    side.set_title("Side cut through the roof (green)")
    for target in (whole, zoom, side):
        views.scale_bar(target)
    legend = [views.patch_key(views.PART, "Layer below: where strands can land", views.EDGE), views.patch_key(views.LIGHT, "This layer", views.EDGE),
              views.patch_key("#cfe8d8", "Roof over air", views.OK), views.line_key(views.OK, "Strand landing on plastic at both ends"),
              views.line_key(views.FAIL, "Strand ending over air")]
    note = (f"the widest of {len(assessed)} roof(s) the check assessed on this part; {first.anchored:.0%} of strands land on plastic "
            f"at both ends, longest {first.longest:.1f} mm")
    return views.View("bridge-layer", fig, legend, note)


def pass_connected(design, finding, part_id):
    """The part from above and from the side, one colour: a single body."""
    mesh = design.mesh(part_id)
    pieces = [shell for shell in mesh.split(only_watertight=False) if shell.volume > 0]
    fig, (top, side) = views.new_figure("two")
    for target, axes in ((top, (0, 1)), (side, (0, 2))):
        for piece in pieces:
            views.silhouette(target, piece, axes, views.PART, z=1)
        low, high = mesh.bounds
        views.frame(target, (low[axes[0]], low[axes[1]], high[axes[0]], high[axes[1]]))
        views.scale_bar(target)
    side.axhline(mesh.bounds[0][2], color=views.EDGE, lw=0.8, ls="--")
    top.set_title("From above")
    side.set_title("From the side (dashed: the bed)")
    return views.View("pieces", fig, [views.patch_key(views.PART, f"The part: {len(pieces)} body")])


def draw_keyholes(design, finding):
    """Estoa R6 as enclosure.keyholes reads it today: the back cut at_depth from the wall, each keyhole's entry and slot
    coloured by its own verdict, with the head of the first common fastener it hangs on drawn where the slot ends.
    (The views script's R6 drawer predates the common-fastener rule and no longer runs.)"""
    import numpy as np
    from matplotlib.patches import Circle
    from shapely.geometry import Polygon
    from pbe.graders import enclosure, placed
    args = design.args("R6")
    piece = design.piece()
    back = views.merged(placed.section(piece.meshes, piece.wall_z + args["at_depth"]))
    holes = [Polygon(ring) for poly in views.polygons_of(back) for ring in poly.interiors]
    found = [keyhole for keyhole in (enclosure._keyhole(hole) for hole in holes) if keyhole is not None]
    fasteners = [enclosure.Fastener.model_validate(f) for f in args["fasteners"]]
    angle = enclosure.AngleLimits.model_validate(args["angle"])
    fig, axes = views.new_figure("two" if found else "one")
    overview = axes[0]
    legend = [views.patch_key(views.PART, f"Printed back, cut {args['at_depth']} mm from the wall", views.EDGE)]
    if not found:
        views.fill(overview, back, fc=views.PART, ec=views.EDGE, lw=0.5)
        for hole in holes:
            views.fill(overview, hole, z=3, fc="none", ec=views.WARN, lw=1.2)
        views.frame(overview, views.bounds_of(back))
        overview.set_title("The back, seen from the front")
        views.scale_bar(overview)
        legend.append(views.line_key(views.WARN, "A hole that isn't a keyhole (no narrower slot off a round entry)"))
        return views.View("back-keyholes", fig, legend, f"{len(holes)} hole(s) in the back, none of them a keyhole")
    up = enclosure._hanging_up(found)
    verdicts = [enclosure._keyhole_verdict(keyhole, up, fasteners, args["entry_margin"], angle) for keyhole in found]

    def draw_all(ax, lw):
        views.fill(ax, back, fc=views.PART, ec=views.EDGE, lw=0.5)
        for keyhole, verdict in zip(found, verdicts):
            centre, entry, slot, direction, travel = keyhole
            colour = views.FAIL if verdict.ok is False else (views.OK if verdict.ok else views.WARN)
            ax.add_patch(Circle(centre, entry / 2, fill=False, ls="--", ec=colour, lw=lw, zorder=4))
            fits = enclosure._hangs_on(entry, slot, fasteners, args["entry_margin"])
            rest = centre + direction * travel
            if fits:
                ax.add_patch(Circle(rest, fits[0].head / 2, fill=False, ec=views.HARDWARE, lw=lw * 1.2, zorder=5))
            ax.annotate("", xy=rest, xytext=centre, arrowprops={"arrowstyle": "-|>", "color": colour, "lw": lw}, zorder=6)
    draw_all(overview, 0.9)
    span = views.bounds_of(back)
    size = max(span[2] - span[0], span[3] - span[1])
    middle = np.array(((span[0] + span[2]) / 2, (span[1] + span[3]) / 2))
    overview.annotate("up", xy=tuple(middle + up * size * 0.2), xytext=tuple(middle), color=views.BOARD,
                      arrowprops={"arrowstyle": "-|>", "color": views.BOARD, "lw": 1.4}, fontsize=7.5, zorder=7)
    views.frame(overview, span)
    overview.set_title("The back, seen from the front")
    views.scale_bar(overview)
    worst = next((k for k, v in zip(found, verdicts) if v.ok is not True), found[0])
    centre, entry, slot, direction, travel = worst
    zoom = axes[1]
    draw_all(zoom, 1.4)
    window = Point(*(centre + direction * travel / 2)).buffer(entry / 2 + travel / 2 + 4)
    views.frame(zoom, window.bounds, pad=0)
    zoom.text(centre[0], centre[1], f"entry {entry:.1f}", fontsize=6.8, ha="center", va="center", zorder=8)
    zoom.set_title(f"Zoomed: slot {slot:.2f} wide")
    views.scale_bar(zoom)
    legend += [views.line_key(views.OK, "Keyhole entry (green: hangs, red: fails, orange: not graded)", "--"),
               views.line_key(views.HARDWARE, "Head of the first common nail or screw it hangs on, where the slot ends"),
               views.line_key(views.BOARD, "Up when it hangs: the way the slots run")]
    return views.View("back-keyholes", fig, legend)


PASS_DRAWERS = {"bridges": pass_bridges, "connected_bodies": pass_connected}
OWN_DRAWERS = {("estoa-light", "R6"): draw_keyholes}
STATES = {True: "pass", False: "fail", None: "not graded"}


def caption(design, finding, note=""):
    """The drawing's alt text: the check, its result and the grader's own words. The image itself carries no caption,
    so the page doesn't print the finding twice."""
    titles = results_site.CHECK_TITLES["*"] | results_site.CHECK_TITLES.get(design.family, {})
    where = f" ({finding['part']})" if finding.get("part") not in ("-", None) else ""
    detail = views.reader_words_keeping(re.sub(r"\s+", " ", finding.get("detail") or "").strip(), [part.id for part in design.sub.parts])
    state = {"pass": "passes", "fail": "fails", "not graded": "not graded"}[STATES[finding.get("ok")]]
    text = f"{titles.get(finding['check'], finding['check'])}{where}: {state}. {detail[:1].upper()}{detail[1:]}"
    return text + (f" ({results_site.reader_words(note)})" if note else "")


def draw(example) -> dict:
    folder = media.RUNS / example["trial"]
    finding = saved_finding(folder, example["check"], example["part"])
    if STATES[finding.get("ok")] != example["outcome"]:
        raise SystemExit(f"{example['trial']}: {example['check']} is {STATES[finding.get('ok')]} today, not {example['outcome']}")
    design = views.load_design(folder)
    check = example["check"]
    if (design.family, check) in OWN_DRAWERS:
        view = OWN_DRAWERS[design.family, check](design, finding)
    elif check in PASS_DRAWERS and finding.get("ok") is True:
        view = PASS_DRAWERS[check](design, finding, example["part"])
    elif check in views.PER_PART:
        view = views.choose(design.family, check)(design, finding, example["part"])
    else:
        drawer = views.choose(design.family, check)
        if drawer is None:
            raise SystemExit(f"no drawer for {design.family} {check}")
        view = drawer(design, finding)
    views.OBJECTS = OBJECTS  # store() writes under the views script's OBJECTS
    owner = example["part"] if example["part"] != "-" else "design"
    state = STATES[finding.get("ok")].replace(" ", "-")
    obj = views.store(views.render(view, ""), f"{views.safe(owner)}-{views.safe(check)}-{state}.webp")
    width, height = picture_size(obj)
    return {"design": example["trial"], "check": check, "part": example["part"], "state": STATES[finding.get("ok")],
            "kind": view.kind, "caption": caption(design, finding, view.note),
            "note": results_site.reader_words(view.note) if view.note else None, "object": obj, "width": width, "height": height}


def picture_size(obj):
    from PIL import Image
    with Image.open(OBJECTS / obj) as picture:
        return picture.size


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--upload-workers", type=int, default=6, help="the media host rate-limits above 6")
    args = parser.parse_args()
    OBJECTS.mkdir(parents=True, exist_ok=True)
    drawn = []
    for example in all_examples():
        print(f"drawing {example['check']} ({example['outcome']}) on {example['trial']}", file=sys.stderr)
        drawn.append(draw(example))
    objects = sorted({item["object"] for item in drawn})
    for obj in objects:
        print(f"  {OBJECTS / obj}", file=sys.stderr)
    if args.no_upload:
        return
    media.OBJECTS, media.LEDGER = OBJECTS, LEDGER
    done, failures = media.upload(objects, args.upload_workers)
    uploaded = set(LEDGER.read_text().split()) if LEDGER.exists() else set()
    if failures or not set(objects) <= uploaded:
        raise SystemExit(f"{len(failures)} uploads failed, so {COMMITTED.name} is left as it was")
    manifest = {"version": VERSION, "views": [{key: (media.url_of(item["object"]) if key == "object" else value)
                                               for key, value in item.items()} for item in drawn]}
    for item in manifest["views"]:
        item["view"] = item.pop("object")
    text = json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert "/Users/" not in text and str(Path.home()) not in text and "results/local" not in text
    COMMITTED.write_text(text)
    print(f"wrote {COMMITTED.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
