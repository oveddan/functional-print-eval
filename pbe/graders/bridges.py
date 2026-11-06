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
from functools import reduce

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point

from pbe.parts.printer import printer

STRAND_SPACING = 0.4  # mm: one nozzle width


def settings():
    """The check's settings as one dict, the form the coupon predictions record them in."""
    return {"layer": printer().layer_mm, **printer().bridging.model_dump()}


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
    borders_hole: bool = False  # its outline runs along a hole its own layer encloses, such as the bolt's


def _layer_at(mesh, z):
    """The cross-section at height z as one polygon with its holes, or None if there's nothing there."""
    cut = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if cut is None:
        return None
    to_2d = np.eye(4)
    to_2d[2, 3] = -z
    planar, _ = cut.to_2D(to_2D=to_2d, check=False)
    # even-odd: XOR of every closed loop gives the layer with its holes
    loops = [loop for loop in planar.polygons_closed if loop is not None and loop.is_valid]
    return reduce(lambda so_far, loop: so_far.symmetric_difference(loop), loops) if loops else None


def layers(mesh: trimesh.Trimesh, layer_h):
    """Cross-section polygons at each layer's mid-height, bed at z = 0."""
    mesh = mesh.copy()
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    found = []
    z = layer_h / 2
    while z < mesh.bounds[1][2]:
        found.append((z, _layer_at(mesh, z)))
        z += layer_h
    return found


def _strands(region, angle, spacing):
    """Parallel lines across the region at the given angle, clipped to it."""
    centre = region.centroid
    reach = max(region.bounds[2] - region.bounds[0], region.bounds[3] - region.bounds[1])
    lines = []
    for offset in np.arange(-reach, reach + spacing, spacing):
        lines.append(LineString([(centre.x - reach, centre.y + offset), (centre.x + reach, centre.y + offset)]))
    rotated = affinity.rotate(MultiLineString(lines), angle, origin=centre)
    strands = []
    for line in rotated.geoms:
        cut = line.intersection(region)
        pieces = cut.geoms if hasattr(cut, "geoms") else [cut]
        strands += [piece for piece in pieces if piece.geom_type == "LineString" and piece.length > spacing / 2]
    return strands


@dataclass
class Direction:
    """Strands laid across a region at one angle."""
    angle: int
    anchored: float  # share of strands that land on solid at both ends
    longest: float
    strands: list  # (LineString, anchored)

    @property
    def score(self):
        """The most strands anchored, then the shortest longest strand."""
        return self.anchored, -self.longest


def _try_direction(region, anchor, angle):
    """Strands across the region at this angle, or None if none cross it."""
    strands = _strands(region, angle, STRAND_SPACING)
    if not strands:
        return None
    anchored = [anchor.contains(Point(strand.coords[0])) and anchor.contains(Point(strand.coords[-1])) for strand in strands]
    longest = max(strand.length for strand in strands)
    return Direction(angle, sum(anchored) / len(anchored), longest, list(zip(strands, anchored)))


def assess(region, support):
    """Try a strand direction every 5 degrees and keep the best, the first if two tie:
    (angle, share anchored, longest, ok, [(strand, anchored)])."""
    bridging = printer().bridging
    anchor = support.buffer(bridging.anchor_tol_mm)
    best = None
    for angle in range(0, 180, 5):
        tried = _try_direction(region, anchor, angle)
        if tried is not None and (best is None or tried.score > best.score):
            best = tried
    ok = best.anchored >= bridging.min_anchored and best.longest <= bridging.max_span_mm
    return best.angle, best.anchored, best.longest, ok, best.strands


def _within(region, support, mm):
    """Is the whole region, but for slivers, this close to the layer below?"""
    return region.difference(support.buffer(mm)).area < 0.05


def _borders_hole(region, layer, mm=1.0):
    """Does at least mm of the region's outline run along a hole the layer encloses? A ring roof around a bolt
    hole does, and so does a roof a slot cuts in two; a ledge whose free edge is the part's outside doesn't."""
    rings = [ring for poly in (layer.geoms if hasattr(layer, "geoms") else [layer]) for ring in getattr(poly, "interiors", [])]
    return sum(region.boundary.intersection(ring.buffer(0.05)).length for ring in rings) >= mm


def _unsupported_regions(layer, below):
    """The parts of a layer with nothing under them, big enough to matter."""
    unsupported = layer.difference(below)
    regions = unsupported.geoms if hasattr(unsupported, "geoms") else [unsupported]
    return [region for region in regions if not region.is_empty and region.area >= 0.5]


def overhangs(mesh: trimesh.Trimesh):
    """Every region in every layer that needs a bridge, with whether it can be bridged."""
    layer_h, bridging = printer().layer_mm, printer().bridging
    found = []
    below = None
    for z, layer in layers(mesh, layer_h):
        if layer is None or below is None:
            below = layer
            continue
        for region in _unsupported_regions(layer, below):
            # an ordinary small overhang: everything is close to the layer below
            if _within(region, below, bridging.small_overhang_mm):
                continue
            angle, share, longest, ok, strands = assess(region, below)
            narrow = _within(region, below, bridging.narrowest_tangled_mm)
            found.append(Overhang(z=round(z - layer_h / 2, 2), region=region, support=below, best_angle=angle, anchored=share,
                                  longest=longest, ok=ok, narrow=narrow, strands=strands, borders_hole=_borders_hole(region, layer)))
        below = layer
    return found


def is_holed_roof(overhang: Overhang) -> bool:
    """A roof that fails the strand test, isn't a narrow ledge, and has a hole cut through it: the shape that
    tangled on the Arca plate and coupon A's H cell, where strands end at the hole. The hole can be a ring
    inside the roof or a slot that cuts it in two; either way it's a hole in the roof's own layer."""
    return not overhang.ok and not overhang.narrow and overhang.borders_hole


def svg(overhang: Overhang, size=520):
    """Picture of one overhang: the layer below, the unsupported region, and the
    strands in the best direction (green: both ends on solid; red: not)."""
    window = overhang.region.buffer(4)
    min_x, min_y, max_x, max_y = window.bounds
    scale = size / max(max_x - min_x, max_y - min_y)
    width, height = (max_x - min_x) * scale, (max_y - min_y) * scale

    def x_px(x):
        return f"{(x - min_x) * scale:.1f}"

    def y_px(y):  # SVG's y runs down
        return f"{(max_y - y) * scale:.1f}"

    def path(geom):
        polys = geom.geoms if hasattr(geom, "geoms") else [geom]
        commands = ""
        for poly in polys:
            if poly.geom_type != "Polygon":
                continue
            for ring in [poly.exterior, *poly.interiors]:
                commands += "M" + " L".join(f"{x_px(x)},{y_px(y)}" for x, y in ring.coords) + " Z "
        return commands

    below = overhang.support.intersection(window.envelope)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}">',
           f'<path d="{path(below)}" fill="#c9d1cc" fill-rule="evenodd"/>',
           f'<path d="{path(overhang.region)}" fill="#f6c89f" fill-rule="evenodd" stroke="#c2410c" stroke-width="1"/>']
    for strand, anchored in overhang.strands:
        (x0, y0), (x1, y1) = strand.coords[0], strand.coords[-1]
        colour = "#2f7a4f" if anchored else "#b42318"
        out.append(f'<line x1="{x_px(x0)}" y1="{y_px(y0)}" x2="{x_px(x1)}" y2="{y_px(y1)}" stroke="{colour}" stroke-width="1.2"/>')
    out.append("</svg>")
    return "\n".join(out)
