"""Where each test-print cell sits in Dan's round 3 photos: the key for the Box test and the crops for the roof test.

Claude's reading of the photos, 2026-11-12, in pixels of the upright photo scaled to 1125 x 1500, written as
fractions. Cell numbers follow the notes in results/predictions/round3-coupons.yaml ("the photo puts cells 10, 9,
8, 7 and 6 down to 1 in that order": large cells down the left column, small ones down the right). The three long
bridges in IMG_6188 are told apart by length: their ends measure about 1160, 930 and 760 px apart, the 100:80:60
ratio of the 100, 80 and 60 mm spans. The five short arcs aren't told apart in the photo or the record.
"""
from pydantic import BaseModel

from pbe.judges.decisions import Edges

W, H = 1125, 1500
DROPBOX_PHOTOS = "Dropbox/Projects/Making Documentation/Print Build Eval/06 Photos"  # under the home folder


class Cell(BaseModel):
    photo: str          # file name in the Dropbox photo folder
    name: str           # how the record names it
    where: str          # how to find it by position, as the Box question puts it
    what: str           # what the crop shows, for the roof question
    edges: Edges
    dan_said: str       # the record's outcome, as written
    clean: bool         # Claude's reading of Dan's words: "ok", "fine", "clean" -> clean; "messed up", "failed" -> not


def _px(left, top, right, bottom) -> Edges:
    return Edges(left=left / W, top=top / H, right=right / W, bottom=bottom / H)


RINGS = "round3-ring-roofs-underside IMG_6164.HEIC"
BRIDGES = "round3b-bridges-underside IMG_6188.HEIC"
GPT_ROOF = "round3b-gpt-roof IMG_6190.HEIC"
STRINGY = "failed: all stringy, strings break"


def _ring(cell, where, box, said, clean, size):
    return Cell(photo=RINGS, name=f"ring roof {cell}", where=where, edges=_px(*box), dan_said=said, clean=clean,
                what=f"one printed ring roof ({size} pocket round a hole) on the underside of a test print")


CELLS = [
    _ring("10", "the top round pocket in the left column of large pockets", (307, 190, 523, 406),
          "ok; a bit loose, fixable by clipping", True, "22 mm stepped"),
    _ring("9", "the second round pocket from the top in the left column of large pockets", (305, 449, 521, 665),
          "messed up", False, "22 mm"),
    _ring("8", "the third round pocket from the top in the left column of large pockets", (333, 755, 493, 915),
          "mostly ok, needs a bit of trimming", True, "16 mm stepped"),
    _ring("7", "the bottom round pocket in the left column of large pockets", (333, 1020, 493, 1180),
          "messed up", False, "16 mm"),
    _ring("6", "the smallest hexagonal hole, at the top of the right column of small pockets", (648, 367, 704, 423),
          "fine", True, "5.7 mm hex"),
    _ring("5", "the larger hexagonal pocket, second from the top in the right column of small pockets",
          (634, 508, 718, 592), "mostly ok; a few strands, not the end of the world", True, "8.1 mm hex"),
    _ring("4", "the third pocket from the top in the right column of small pockets", (621, 640, 731, 750),
          "messed up", False, "11.5 mm"),
    _ring("3", "the fourth pocket from the top in the right column of small pockets", (626, 795, 726, 895),
          "messed up", False, "10.5 mm"),
    _ring("2", "the fifth pocket from the top in the right column of small pockets", (631, 955, 721, 1045),
          "messed up", False, "9.5 mm"),
    _ring("1", "the bottom pocket in the right column of small pockets", (636, 1110, 716, 1190),
          "mostly ok", True, "8.5 mm"),
]

_BRIDGE = "a printed bridge (a bar of plastic printed across a gap between two blocks)"
_ARC = "a short printed roof strip between two blocks"
CELLS += [
    Cell(photo=BRIDGES, name="100 mm span", where="the longest bar, lying diagonally", edges=_px(225, 160, 575, 1320),
         what=_BRIDGE, dan_said=STRINGY, clean=False),
    Cell(photo=BRIDGES, name="80 mm span", where="the second-longest bar, right of centre", edges=_px(600, 235, 840, 1180),
         what=_BRIDGE, dan_said=STRINGY, clean=False),
    Cell(photo=BRIDGES, name="60 mm span", where="the third-longest bar, in the middle", edges=_px(500, 205, 665, 965),
         what=_BRIDGE, dan_said=STRINGY, clean=False),
]
CELLS += [Cell(photo=BRIDGES, name=f"roof crop arc {i}", where="", edges=_px(*box), what=_ARC, dan_said=STRINGY,
               clean=False)
          for i, box in enumerate([(135, 340, 230, 830), (215, 315, 325, 855), (725, 470, 870, 940),
                                   (785, 465, 985, 925), (875, 470, 1035, 945)], start=1)]
CELLS.append(Cell(photo=GPT_ROOF, name="GPT-6.1 Sol's roof crop", where="", edges=_px(0, 0, W, H),
                  what="a small printed part held in the fingers, including a roof printed over a pocket",
                  dan_said="clean", clean=True))


def references_for(judged: Cell, per_verdict: int = 2) -> list[Cell]:
    """Leave-one-out examples for judging `judged`: `per_verdict` cells that worked and as many that failed,
    never `judged` itself, from other photos first, then the same photo, in CELLS order. Claude's call: the
    ring-roof photo holds 5 of the 6 cells that worked, so its cells mostly get examples from that photo."""
    others = [c for c in CELLS if c.name != judged.name or c.photo != judged.photo]
    ordered = [c for c in others if c.photo != judged.photo] + [c for c in others if c.photo == judged.photo]
    worked = [c for c in ordered if c.clean][:per_verdict]
    failed = [c for c in ordered if not c.clean][:per_verdict]
    return worked + failed
