"""Pictures and meshes for the public results site: for every saved design, a thumbnail of each part, a mesh
the site's 3D viewer loads on demand and, where the grader's own geometry can find it, the failing feature in
red. No model calls.

    uv run --with pyvista python scripts/results_site_media.py              # build, render, upload, write the manifest
    uv run --with pyvista python scripts/results_site_media.py --no-upload  # everything but the upload

A design is any folder under results/runs holding a submission.yaml: a trial, or one arm of a coupon loop replay
(baseline, feedback, neutral), whose parts are built without its test prints, as the loop graded them. parts/ isn't
committed, so a design whose meshes aren't on this machine is built again from its submission first, in the
sandbox (pbe/parts/build.py).

The images and meshes go to the R2 media host under content-addressed keys (print-build-eval/site/<sha256-8>/<name>),
never into the repo. Only the manifest of their URLs is committed: scripts/results_site_media.json. Work is kept under
results/local/site-media/ (one record per design, the rendered files, the upload ledger), so a re-run only does what's
new. pyvista comes in with `uv run --with` so the project's own dependencies don't change.

A highlight marks where a failed check looked, using the same code the grader ran, never a second grading:
- bridges: the faces of every overhang pbe.graders.bridges.overhangs finds unbridgeable (not ok, not a narrow ledge);
- connected_bodies: every piece but the largest (a final part), or the pieces off the bed (a test print), split as
  the check splits them;
- the nut knob's R3 and R4: the hex pocket pbe.graders.nuts._nuts_pocket reads, which both checks grade.
Other checks get no highlight; the site shows their text. An Estoa design also gets its assembled view (`scene`),
from scripts/assembly_scene.py, with each failed requirement drawn where its reason says.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs"
WORK = ROOT / "results/local/site-media"
RECORDS = WORK / "designs"
OBJECTS = WORK / "objects"
LEDGER = WORK / "uploaded.txt"
MANIFEST = Path(__file__).with_suffix(".json")
BUILD_NOTE = ".site-build.json"  # in parts/: what the rebuild made of each part, so a failed build isn't retried

BUCKET = "danoved-media"
KEY_PREFIX = "print-build-eval/site"
BASE_URL = "https://media.danoved.xyz"
CACHE_CONTROL = "public, max-age=31536000, immutable"
CONTENT_TYPES = {".webp": "image/webp", ".glb": "model/gltf-binary"}

VERSION = 1  # bump to re-render every design
THUMB = (640, 512)
SUPERSAMPLE = 2
PART_RGB = (176, 186, 196)
RED_RGB = (222, 52, 40)
EDGE_RGB = "#2f3a45"
WEBP_QUALITY = 80
FINDINGS_FILES = ("grades.json", "loop.json", "replay.json")
LOOP_ARM_FILE = "loop.json"


# ---- finding the designs ----

def design_folders():
    return sorted(path.parent for path in RUNS.glob("**/submission.yaml"))


def rel(folder):
    return folder.relative_to(RUNS).as_posix()


def record_path(folder):
    return RECORDS / (re.sub(r"[^\w.-]+", "__", rel(folder)) + ".json")


def saved_findings(folder):
    """(findings as saved, declined): from the trial's grades, the loop arm's record or the crash replay's."""
    for name in FINDINGS_FILES:
        path = folder / name
        if path.exists():
            saved = json.loads(path.read_text())
            return saved.get("findings") or [], bool(saved.get("declined"))
    return [], False


def task_of(folder):
    for name in FINDINGS_FILES:
        if (folder / name).exists():
            return json.loads((folder / name).read_text()).get("task", "")
    return ""


# ---- building ----

def submission_to_build(folder):
    """The submission as graded: a loop arm without its test prints (coupon_loop.without_coupons, as
    results_page.arm_parts builds it), a trial whole."""
    from pbe.parts import submission
    from pbe.runner import coupon_loop
    sub = submission.load(folder / "submission.yaml")
    return coupon_loop.without_coupons(sub) if (folder / LOOP_ARM_FILE).exists() else sub


def ensure_built(folder, sub):
    """Build the parts into folder/parts if they aren't there (results_page.ensure_parts does the same, but this
    keeps each part's error, so a design that won't build isn't rebuilt on every run). {part id: error or ""}."""
    from pbe.parts.build import build_parts
    parts = folder / "parts"
    note = parts / BUILD_NOTE
    if note.exists():
        return json.loads(note.read_text())
    if all((parts / f"{part.id}.stl").exists() for part in sub.parts):  # built before, by another script
        errors = {part.id: "" for part in sub.parts}
    else:
        errors = {part_id: built.error for part_id, built in build_parts(sub, parts).items()}
    parts.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps(errors, indent=1))
    return errors


def short_reason(error):
    """One line, at most 160 characters, with no local paths: the manifest is public."""
    error = re.sub(r"(/Users|/home|/private|/var|/tmp)/\S*", "<path>", error)
    return re.sub(r"\s+", " ", error).strip()[:160] or "didn't build"


# ---- highlights: where a failed check looked ----

def _bridge_faces(mesh):
    """Faces of the overhangs the bridge check finds unbridgeable, and a thin sheet for any it can't match to faces."""
    import shapely
    from pbe.graders.bridges import overhangs
    from pbe.parts.printer import printer
    layer = printer().layer_mm
    bottom = mesh.bounds[0][2]
    centres, normals = mesh.triangles_center, mesh.face_normals
    faces, sheets = set(), []
    for found in overhangs(mesh):
        if found.ok or found.narrow:
            continue
        z = found.z + bottom  # overhangs() puts the bed at z = 0
        near = (centres[:, 2] > z - 0.05) & (centres[:, 2] < z + layer + 0.05) & (normals[:, 2] < -0.2)
        inside = near & shapely.contains_xy(found.region.buffer(0.4), centres[:, 0], centres[:, 1])
        if inside.any():
            faces.update(np.flatnonzero(inside).tolist())
        else:
            sheets += _sheets(found.region, z)
    return faces, sheets


def _sheets(region, z):
    region = region.simplify(0.05)
    polygons = getattr(region, "geoms", [region])
    found = []
    for polygon in polygons:
        if polygon.geom_type == "Polygon" and polygon.area > 0.5:
            sheet = trimesh.creation.extrude_polygon(polygon, 0.4)
            sheet.apply_translation((0, 0, z - 0.45))
            found.append(sheet)
    return found


def _components(mesh):
    """The mesh's pieces as face index arrays, split as the connected_bodies check splits it (a sealed void, whose
    volume is negative, isn't a piece)."""
    groups = trimesh.graph.connected_components(mesh.face_adjacency, nodes=np.arange(len(mesh.faces)), min_len=1)
    pieces = []
    for group in groups:
        piece = mesh.submesh([group], append=True)
        if piece.volume > 0:
            pieces.append((group, piece))
    return pieces


def _loose_faces(mesh, role):
    pieces = _components(mesh)
    if len(pieces) < 2 and role != "coupon":
        return set()
    if role == "coupon":
        bed = mesh.bounds[0][2]
        return {int(face) for group, piece in pieces if piece.bounds[0][2] > bed + 0.01 for face in group}
    largest = max(pieces, key=lambda found: found[1].volume)
    return {int(face) for group, piece in pieces if group is not largest[0] for face in group}


def _nut_pocket_faces(mesh, task):
    """Faces of the hex pocket the nut knob's R3 and R4 read (nuts._nuts_pocket): within the hexagon's corners,
    over the pocket's height."""
    from pbe.graders import nuts
    from pbe.parts import catalog
    from pbe.runner import tasks
    variant = task.split("/")[1] if "/" in task else ""
    nut = tasks.variant_values("nut-knob", variant)["nut"] if variant else None
    if nut is None:
        return set()
    af = catalog.resolve(f"ISO 4032 {nut}")["af"]
    found = nuts._nuts_pocket(mesh, af)
    if found is None:
        return set()
    centres = mesh.triangles_center
    reach = found.across / np.sqrt(3) + 0.3  # the hexagon's corner radius, and a little
    distance = np.hypot(centres[:, 0] - found.centre.x, centres[:, 1] - found.centre.y)
    inside = (distance <= reach) & (centres[:, 2] >= found.z[0] - 0.05) & (centres[:, 2] <= found.z[1] + 0.05)
    return set(np.flatnonzero(inside).tolist())


def highlight(mesh, role, failed, task):
    """(face indices, extra sheets, checks located) for one part's failed checks."""
    faces, sheets, located = set(), [], []
    for check in sorted({finding["check"] for finding in failed}):
        found, extra = set(), []
        if check == "bridges":
            found, extra = _bridge_faces(mesh)
        elif check == "connected_bodies":
            found = _loose_faces(mesh, role)
        elif check in ("R3", "R4") and task.startswith("nut-knob/"):
            found = _nut_pocket_faces(mesh, task)
        if found or extra:
            faces |= found
            sheets += extra
            located.append(check)
    return faces, sheets, located


# ---- rendering ----

VIEWS = [(elev, azim) for elev in (28, -28) for azim in (-55, 35, 125, -145)]


def _direction(elev, azim):
    """Unit vector from the part towards the camera, Z up."""
    e, a = np.radians(elev), np.radians(azim)
    return np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])


def choose_view(mesh, faces):
    """A 3/4 view. With a highlight, the one that faces the most red area (from below for an overhang);
    without, the top view that faces the most triangles, where holes, fillets and lettering are."""
    normals, areas = mesh.face_normals, mesh.area_faces
    red = np.zeros(len(mesh.faces), bool)
    red[list(faces)] = True

    def score(view):
        facing = normals @ _direction(*view)
        detail = int((facing > 0.2).sum())
        if red.any():
            return float((areas[red] * np.clip(facing[red], 0, None)).sum()), detail
        return (0.0 if view[0] > 0 else -1.0), detail
    return max(VIEWS, key=score)


def _polydata(mesh, faces, rgb):
    import pyvista as pv
    data = pv.PolyData.from_regular_faces(np.asarray(mesh.vertices), np.asarray(mesh.faces))
    colours = np.tile(np.array(PART_RGB, np.uint8), (len(mesh.faces), 1))
    if faces:
        colours[list(faces)] = rgb
    data.cell_data["rgb"] = colours
    return data


def _frame(plotter, mesh, direction):
    """Point an orthographic camera along `direction` and fit the part to the frame with a small margin."""
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(up, direction)
    right /= np.linalg.norm(right)
    true_up = np.cross(direction, right)
    centre = mesh.bounds.mean(axis=0)
    span = float(np.linalg.norm(mesh.extents)) or 1.0
    points = mesh.vertices - centre
    across, tall = np.ptp(points @ right), np.ptp(points @ true_up)
    middle = centre + right * ((points @ right).max() + (points @ right).min()) / 2 \
        + true_up * ((points @ true_up).max() + (points @ true_up).min()) / 2
    plotter.camera.position = tuple(middle + direction * span * 3)
    plotter.camera.focal_point = tuple(middle)
    plotter.camera.up = tuple(true_up)
    plotter.enable_parallel_projection()
    aspect = THUMB[0] / THUMB[1]
    plotter.camera.parallel_scale = max(tall / 2, across / 2 / aspect) * 1.08
    plotter.reset_camera_clipping_range()


def render(mesh, faces, sheets, view, out_png):
    import pyvista as pv
    size = (THUMB[0] * SUPERSAMPLE, THUMB[1] * SUPERSAMPLE)
    plotter = pv.Plotter(off_screen=True, window_size=size, lighting="none")
    plotter.add_light(pv.Light(light_type="headlight", intensity=0.55))
    plotter.add_light(pv.Light(position=(-1, 1, 2), light_type="camera light", intensity=0.45))
    plotter.add_light(pv.Light(position=(1, -0.5, 0.3), light_type="camera light", intensity=0.2))
    data = _polydata(mesh, faces, RED_RGB)
    plotter.add_mesh(data, scalars="rgb", rgb=True, smooth_shading=False, ambient=0.28, diffuse=0.75,
                     specular=0.12, specular_power=18, show_scalar_bar=False)
    for sheet in sheets:
        plotter.add_mesh(pv.wrap(sheet), color=RED_RGB, ambient=0.4, diffuse=0.7)
    edges = data.extract_feature_edges(feature_angle=35, boundary_edges=True, non_manifold_edges=False,
                                       manifold_edges=False)
    if edges.n_points:
        plotter.add_mesh(edges, color=EDGE_RGB, line_width=1.6 * SUPERSAMPLE, opacity=0.55)
    plotter.add_silhouette(data, color=EDGE_RGB, line_width=1.4 * SUPERSAMPLE)
    _frame(plotter, mesh, _direction(*view))
    image = plotter.screenshot(None, transparent_background=True, return_img=True)
    plotter.close()
    plotter.deep_clean()
    return image


def red_pixels(image):
    rgb = image[..., :3].astype(int)
    return int(((rgb[..., 0] > 70) & (rgb[..., 0] > 2 * rgb[..., 1]) & (image[..., 3] > 0)).sum())  # red, lit or in shade


def to_webp(image, path):
    from PIL import Image
    picture = Image.fromarray(image, "RGBA").resize(THUMB, Image.LANCZOS)
    picture.save(path, "WEBP", quality=WEBP_QUALITY, method=6, alpha_quality=90)


def drawn(image):
    """Did the render draw the part? Under GPU memory pressure an offscreen render can come back empty."""
    return (image[..., 3] > 0).mean() > 0.01


def render_checked(mesh, faces, sheets, view, path):
    for attempt in range(3):
        image = render(mesh, faces, sheets, view, path)
        if drawn(image):
            return image
    raise RuntimeError("the render came back empty three times")


def thumbnail(mesh, faces, sheets, path):
    """Render from the chosen view; with a highlight that the view hides, try the next best views."""
    first = choose_view(mesh, faces)
    image = render_checked(mesh, faces, sheets, first, path)
    if faces and red_pixels(image) < 200:
        for view in VIEWS:
            if view == first:
                continue
            tried = render_checked(mesh, faces, sheets, view, path)
            if red_pixels(tried) > red_pixels(image):
                image = tried
            if red_pixels(image) >= 200:
                break
    to_webp(image, path)


# ---- the files ----

def glb_bytes(mesh):
    return trimesh.exchange.gltf.export_glb(trimesh.Scene(mesh), include_normals=False)


def store(data: bytes, name):
    """Save bytes under their content hash: (relative object path) == the key's tail."""
    digest = hashlib.sha256(data).hexdigest()[:8]
    path = OBJECTS / digest / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return f"{digest}/{name}"


def safe(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)[:60] or "part"


def part_entry(folder, part_id, role, failed, task):
    stl = folder / "parts" / f"{part_id}.stl"
    mesh = trimesh.load(stl, force="mesh")
    if len(mesh.faces) == 0:
        return {"id": part_id, "role": role, "thumb": None, "mesh": None, "highlight": None, "highlight_checks": [],
                "size_mm": [0.0, 0.0, 0.0]}
    faces, sheets, located = highlight(mesh, role, failed, task)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "thumb.webp"
        thumbnail(mesh, faces, sheets, png)
        thumb = store(png.read_bytes(), f"{safe(part_id)}.webp")
    marked = None
    if faces or sheets:
        pieces = ([mesh.submesh([sorted(faces)], append=True)] if faces else []) + sheets
        marked = store(glb_bytes(trimesh.util.concatenate(pieces)), f"{safe(part_id)}-highlight.glb")
    return {"id": part_id, "role": role, "thumb": thumb, "mesh": store(glb_bytes(mesh), f"{safe(part_id)}.glb"),
            "highlight": marked, "highlight_checks": located,
            "size_mm": [round(float(v), 2) for v in mesh.extents]}


def scene_entry(folder, sub, findings, declined, slug):
    """The assembled view (scripts/assembly_scene.py) with each layer saved as a GLB, or None."""
    if sub.assembly is None:
        return None
    sys.path.insert(0, str(ROOT / "scripts"))
    import assembly_scene
    from pbe.assumptions import Assumed
    counted = [] if declined else [SimpleNamespace(**finding) for finding in findings if not finding.get("test_print")]
    record = SimpleNamespace(counted_findings=counted)
    with tempfile.TemporaryDirectory() as tmp:
        names = {part.id: part.id for part in sub.parts if (folder / "parts" / f"{part.id}.stl").exists()}
        drawn = assembly_scene.scene(sub, record, Assumed.load_if_saved(folder), folder / "parts", Path(tmp), slug, names)
        if drawn is None:
            return None
        for layer in drawn["layers"]:
            for part in layer["parts"]:
                if layer["key"] == "printed":
                    part["part"] = part.pop("name")
                else:
                    text = (Path(tmp) / f"{part.pop('name')}.txt").read_text()
                    import base64
                    import io
                    mesh = trimesh.load(io.BytesIO(base64.b64decode(text)), file_type="stl", force="mesh")
                    part["mesh"] = store(glb_bytes(mesh), f"scene-{layer['key']}.glb")
    return drawn


def process(folder):
    """One design's record: its parts' files, or why it has none. Never raises."""
    try:
        return _process(folder)
    except Exception as e:  # a design that can't be drawn mustn't stop the rest
        return {"rel": rel(folder), "version": VERSION, "built": False,
                "error": short_reason(f"{type(e).__name__}: {e}"), "parts": [], "scene": None}


def owner(finding, sub):
    """The part a finding is about. A requirement on a single-part task is saved with part "-": it's about the one
    final part (sections.single_final), if there is exactly one."""
    ids = [part.id for part in sub.parts]
    if finding.get("part") in ids:
        return finding["part"]
    finals = [part.id for part in sub.parts if part.role == "final"]
    return finals[0] if len(finals) == 1 else None


def _process(folder):
    sub = submission_to_build(folder)
    errors = ensure_built(folder, sub)
    findings, declined = saved_findings(folder)
    failed = [] if declined else [finding for finding in findings if finding.get("ok") is False]
    task = task_of(folder)
    roles = {part.id: part.role for part in sub.parts}
    parts = []
    for part in sub.parts:
        if errors.get(part.id) or not (folder / "parts" / f"{part.id}.stl").exists():
            continue
        mine = [finding for finding in failed if owner(finding, sub) == part.id]
        parts.append(part_entry(folder, part.id, roles[part.id], mine, task))
    broken = {part_id: error for part_id, error in errors.items() if error}
    error = "; ".join(f"{part_id}: {short_reason(error)}" for part_id, error in sorted(broken.items())) or None
    if not parts:
        error = error or ("no final part: the design holds only test prints" if not sub.parts else "no parts")
        return {"rel": rel(folder), "version": VERSION, "built": False, "error": error, "parts": [],
                "scene": None}
    try:
        scene = scene_entry(folder, sub, findings, declined, safe(rel(folder)))
    except Exception as e:  # the view helps read a design; one that can't be drawn mustn't lose the parts
        print(f"no scene for {rel(folder)}: {type(e).__name__}: {e}", file=sys.stderr)
        scene = None
    parts.sort(key=lambda part: (part["role"] != "final", part["id"]))
    return {"rel": rel(folder), "version": VERSION, "built": True, "error": error, "parts": parts, "scene": scene}


def work(folder):
    """Process one design unless its record is current, and save the record."""
    path = record_path(folder)
    if path.exists():
        saved = json.loads(path.read_text())
        if saved.get("version") == VERSION:
            return saved
    record = process(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, sort_keys=True))
    return record


# ---- uploading ----

def objects_in(record):
    found = []
    for part in record["parts"]:
        found += [part[key] for key in ("thumb", "mesh", "highlight") if part.get(key)]
    for layer in (record.get("scene") or {}).get("layers", []):
        found += [part["mesh"] for part in layer["parts"] if part.get("mesh")]
    return found


def key_of(obj):
    return f"{KEY_PREFIX}/{obj}"


def url_of(obj):
    return f"{BASE_URL}/{key_of(obj)}" if obj else None


def put(obj):
    path = OBJECTS / obj
    command = ["npx", "--yes", "wrangler", "r2", "object", "put", f"{BUCKET}/{key_of(obj)}", f"--file={path}", "--remote",
               f"--cache-control={CACHE_CONTROL}", f"--content-type={CONTENT_TYPES[path.suffix]}"]
    for attempt in range(3):
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode == 0:
            return obj, ""
    return obj, (done.stderr.strip().splitlines() or ["failed"])[-1][:200]


def upload(objects, workers):
    """Put every object not yet in the ledger. Keys are content-addressed, so nothing is ever overwritten
    with different bytes."""
    done = set(LEDGER.read_text().split()) if LEDGER.exists() else set()
    todo = sorted(set(objects) - done)
    total = sum((OBJECTS / obj).stat().st_size for obj in todo)
    print(f"uploading {len(todo)} objects, {total / 1e6:.1f} MB ({len(done)} already up)", file=sys.stderr)
    failures = []
    with ThreadPoolExecutor(workers) as pool, LEDGER.open("a") as ledger:
        for count, (obj, error) in enumerate(pool.map(put, todo), 1):
            if error:
                failures.append((obj, error))
            else:
                ledger.write(obj + "\n")
                ledger.flush()
            if count % 200 == 0:
                print(f"  {count}/{len(todo)}", file=sys.stderr)
    for obj, error in failures[:20]:
        print(f"  upload failed: {obj}: {error}", file=sys.stderr)
    return len(todo) - len(failures), failures


# ---- the manifest ----

def manifest_part(part):
    return {"id": part["id"], "role": part["role"], "thumb": url_of(part["thumb"]), "mesh": url_of(part["mesh"]),
            "highlight": url_of(part["highlight"]), "highlight_checks": part["highlight_checks"], "size_mm": part["size_mm"]}


def manifest_scene(scene, parts):
    if not scene:
        return None
    meshes = {part["id"]: url_of(part["mesh"]) for part in parts}
    layers = []
    for layer in scene["layers"]:
        drawn = [{"mesh": meshes.get(part["part"]) if "part" in part else url_of(part["mesh"]), "matrix": part["matrix"],
                  **({"part": part["part"]} if "part" in part else {})} for part in layer["parts"]]
        layers.append({"key": layer["key"], "label": layer["label"], "color": layer["color"], "parts": drawn})
    return {"layers": layers, "fails": scene["fails"], "assumed_fails": scene["assumed_fails"]}


def write_manifest(records):
    designs = {}
    for record in records:
        designs[record["rel"]] = {"built": record["built"], "error": record["error"],
                                  "parts": [manifest_part(part) for part in record["parts"]],
                                  "scene": manifest_scene(record.get("scene"), record["parts"])}
    text = json.dumps({"designs": designs}, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    assert "/Users/" not in text and str(Path.home()) not in text
    MANIFEST.write_text(text)


def saved_records():
    """Every current record on disk whose design is still in results/runs."""
    wanted = {rel(folder) for folder in design_folders()}
    records = [json.loads(path.read_text()) for path in sorted(RECORDS.glob("*.json"))]
    return [record for record in records if record["rel"] in wanted and record.get("version") == VERSION]


def report(records):
    built = [record for record in records if record["built"]]
    parts = [part for record in built for part in record["parts"]]
    reasons = Counter(re.sub(r"[\d.]+", "N", (record["error"] or "").split(": ", 1)[-1])[:70]
                      for record in records if not record["built"])
    checks = Counter(check for part in parts for check in part["highlight_checks"])
    sizes = sorted((OBJECTS / part["mesh"]).stat().st_size for part in parts if part["mesh"])
    thumbs = sorted((OBJECTS / part["thumb"]).stat().st_size for part in parts if part["thumb"])
    print(f"designs {len(records)}, built {len(built)}, failed {len(records) - len(built)}; parts {len(parts)}", file=sys.stderr)
    print(f"highlights by check: {dict(checks)}; scenes {sum(1 for r in built if r.get('scene'))}", file=sys.stderr)
    if sizes:
        q = lambda values, f: values[min(int(f * len(values)), len(values) - 1)] / 1e3
        print(f"mesh KB: median {q(sizes, .5):.0f}, p90 {q(sizes, .9):.0f}, max {sizes[-1] / 1e3:.0f}; "
              f"over 1 MB {sum(s > 1e6 for s in sizes)}", file=sys.stderr)
        print(f"thumb KB: median {q(thumbs, .5):.1f}, p90 {q(thumbs, .9):.1f}, max {thumbs[-1] / 1e3:.1f}", file=sys.stderr)
    for reason, count in reasons.most_common(15):
        print(f"  failed x{count}: {reason}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, help="process at most this many designs")
    parser.add_argument("--only", help="only designs whose path under results/runs contains this")
    parser.add_argument("--no-upload", action="store_true", help="build and render, but don't upload")
    parser.add_argument("--workers", type=int, default=6, help="more can run the GPU out of memory, and offscreen renders come back empty")
    parser.add_argument("--upload-workers", type=int, default=8)
    args = parser.parse_args()
    RECORDS.mkdir(parents=True, exist_ok=True)
    OBJECTS.mkdir(parents=True, exist_ok=True)
    folders = [folder for folder in design_folders() if not args.only or args.only in rel(folder)]
    folders = folders[:args.limit] if args.limit else folders
    print(f"{len(folders)} designs", file=sys.stderr)
    with Pool(args.workers, maxtasksperchild=20) as pool:
        for count, _ in enumerate(pool.imap_unordered(work, folders), 1):
            if count % 25 == 0:
                print(f"  {count}/{len(folders)}", file=sys.stderr)
    records = saved_records()
    report(records)
    objects = sorted({obj for record in records for obj in objects_in(record)})
    total = sum((OBJECTS / obj).stat().st_size for obj in objects)
    print(f"{len(objects)} objects, {total / 1e6:.1f} MB", file=sys.stderr)
    if not args.no_upload:
        uploaded, failures = upload(objects, args.upload_workers)
        print(f"uploaded {uploaded}; {len(failures)} failed", file=sys.stderr)
    write_manifest(records)


if __name__ == "__main__":
    main()
