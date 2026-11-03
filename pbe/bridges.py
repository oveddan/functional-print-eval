"""Predict overhangs that will print as loose strands, before printing.

Slice the part from the bed up, as the printer will. In each layer, the area with
nothing under it in the layer below has to be bridged: strands of plastic stretched
over air. A strand only prints cleanly if both its ends land on solid material.
So for each unsupported region, try strand directions every few degrees and ask
whether, in some direction, (nearly) every strand starts and ends on the layer
below within the printer's longest clean span. A hole cut through a bridge fails
in every direction, because some strands always end at the hole. That is the
Arca plate's first print (and Estoa's sealed leg-pocket hole).

Material within a short distance of the layer below is an ordinary small
overhang and is skipped. A ledge wider than that but narrower than anything seen to
tangle (a nut pocket's roof around its bolt hole) fails the strand test without any
print to back it up, so it's reported as not measured, never as a pass.
"""
from dataclasses import dataclass, field
from functools import cache, reduce
from pathlib import Path

import numpy as np
import trimesh
import yaml
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point

ROOT = Path(__file__).resolve().parents[1]


@cache
def settings():
    p = yaml.safe_load((ROOT / "catalog/printer.yaml").read_text())
    return {"layer": p["layer_mm"], **p["bridging"]}


@dataclass
class Overhang:
    z: float
    region: object  # shapely Polygon
    support: object  # the layer below
    best_angle: float
    anchored: float  # share of strands anchored at both ends in the best direction
    longest: float
    ok: bool  # some direction's strands land on solid at both ends
    narrow: bool  # narrower than anything seen to tangle, so a failed strand test isn't settled
    strands: list = field(default_factory=list)  # (LineString, anchored) in the best direction


def layers(mesh: trimesh.Trimesh, layer_h):
    """Cross-section polygons at each layer's mid-height, bed at z = 0."""
    mesh = mesh.copy()
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    out = []
    z = layer_h / 2
    while z < mesh.bounds[1][2]:
        sec = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
        poly = None
        if sec is not None:
            to_2d = np.eye(4)
            to_2d[2, 3] = -z
            planar, _ = sec.to_2D(to_2D=to_2d, check=False)
            # even-odd: XOR of every closed loop gives the layer with its holes
            loops = [p for p in planar.polygons_closed if p is not None and p.is_valid]
            poly = reduce(lambda a, b: a.symmetric_difference(b), loops) if loops else None
        out.append((z, poly))
        z += layer_h
    return out


def _strands(region, angle, spacing):
    """Parallel lines across the region at the given angle, clipped to it."""
    c = region.centroid
    r = max(region.bounds[2] - region.bounds[0], region.bounds[3] - region.bounds[1])
    lines = []
    for off in np.arange(-r, r + spacing, spacing):
        lines.append(LineString([(c.x - r, c.y + off), (c.x + r, c.y + off)]))
    rotated = affinity.rotate(MultiLineString(lines), angle, origin=c)
    segs = []
    for line in rotated.geoms:
        cut = line.intersection(region)
        parts = cut.geoms if hasattr(cut, "geoms") else [cut]
        segs += [s for s in parts if s.geom_type == "LineString" and s.length > spacing / 2]
    return segs


def assess(region, support, s):
    anchor = support.buffer(s["anchor_tol_mm"])
    best = None
    for angle in range(0, 180, 5):
        segs = _strands(region, angle, 0.4)
        if not segs:
            continue
        flags = [anchor.contains(Point(seg.coords[0])) and anchor.contains(Point(seg.coords[-1])) for seg in segs]
        share = sum(flags) / len(flags)
        longest = max(seg.length for seg in segs)
        score = (share, -longest)
        if best is None or score > best[0]:
            best = (score, angle, share, longest, list(zip(segs, flags)))
    _, angle, share, longest, strands = best
    ok = share >= s["min_anchored"] and longest <= s["max_span_mm"]
    return angle, share, longest, ok, strands


def _within(region, support, mm):
    """Is the whole region, but for slivers, this close to the layer below?"""
    return region.difference(support.buffer(mm)).area < 0.05


def overhangs(mesh: trimesh.Trimesh):
    """Every region in every layer that needs a bridge, with whether it can be bridged."""
    s = settings()
    found = []
    prev = None
    for z, poly in layers(mesh, s["layer"]):
        if poly is not None and prev is not None:
            unsupported = poly.difference(prev)
            parts = unsupported.geoms if hasattr(unsupported, "geoms") else [unsupported]
            for region in parts:
                if region.is_empty or region.area < 0.5:
                    continue
                # an ordinary small overhang: everything is close to the layer below
                if _within(region, prev, s["small_overhang_mm"]):
                    continue
                angle, share, longest, ok, strands = assess(region, prev, s)
                narrow = _within(region, prev, s["narrowest_tangled_mm"])
                found.append(Overhang(round(z - s["layer"] / 2, 2), region, prev, angle, share, longest, ok, narrow, strands))
        prev = poly
    return found


def svg(o: Overhang, size=520):
    """Picture of one overhang: the layer below, the unsupported region, and the
    strands in the best direction (green: both ends on solid; red: not)."""
    minx, miny, maxx, maxy = o.region.buffer(4).bounds
    scale = size / max(maxx - minx, maxy - miny)
    w, h = (maxx - minx) * scale, (maxy - miny) * scale

    def pt(x, y):
        return f"{(x - minx) * scale:.1f},{(maxy - y) * scale:.1f}"

    def path(geom):
        polys = geom.geoms if hasattr(geom, "geoms") else [geom]
        d = ""
        for p in polys:
            if p.geom_type != "Polygon":
                continue
            for ring in [p.exterior, *p.interiors]:
                d += "M" + " L".join(pt(x, y) for x, y in ring.coords) + " Z "
        return d

    window = o.region.buffer(4).envelope
    below = o.support.intersection(window)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">',
           f'<path d="{path(below)}" fill="#c9d1cc" fill-rule="evenodd"/>',
           f'<path d="{path(o.region)}" fill="#f6c89f" fill-rule="evenodd" stroke="#c2410c" stroke-width="1"/>']
    for seg, good in o.strands:
        (x0, y0), (x1, y1) = seg.coords[0], seg.coords[-1]
        out.append(f'<line x1="{pt(x0, y0).split(",")[0]}" y1="{pt(x0, y0).split(",")[1]}" '
                   f'x2="{pt(x1, y1).split(",")[0]}" y2="{pt(x1, y1).split(",")[1]}" '
                   f'stroke="{"#2f7a4f" if good else "#b42318"}" stroke-width="1.2"/>')
    out.append("</svg>")
    return "\n".join(out)
