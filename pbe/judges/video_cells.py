"""Which round 3 clip shows which test-print cells, with the question asked about each and the recorded answer.

The key is results/predictions/round3-coupons.yaml and round3b-roofs.yaml (round 3's records), which name the clip for
each cell. The clips are in Dan's Dropbox (`04 Test print footage`); the runner makes a short H.264 copy of each in a
temp folder and sends it inline. The masters are never touched or copied.

How a question names a cell: the record says which clip shows it but not the second it appears at, so each question
names a cell by the order it's tried in. Claude's reading, 2026-11-12, by clip:

- Bolt holes (IMG_6162 the M8 bolt, IMG_6163 the 1/4-20): Dan tries three holes per clip, about ten seconds each.
  The record reads his names "from the left" as smallest first; this assumes he tried them in the order he named them.
  The holes can't be told apart in the frames (his hands cover the dots), so the order is an assumption.
- Nut pockets, thumb press (IMG_6174): Dan says each result aloud as he goes. The order is from his words: three M5
  pockets down the first row (R2, R1, U3, per the record), five down the second (L2, L1, R5, R4, R3), then the two M3s.
  His closing line, "the only successful one was the bottom row M5, second one", is L1.
- Horn pockets (IMG_6186): three pockets, one fits ("2 are too big, one fits nicely"); the record's notes say the clip
  shows the horn staying in when the plate is tipped on edge.
- Bridges tested (IMG_6158): every bridge failed, "all stringy, strings break".

Left out, because the record can't key a question by order: the bearing seats (IMG_6171/6172: the seats aren't tried
in seat order and the clip is cut), and the bolt-pressed nut clip (IMG_6179: no words, order not recorded).
"""
from pydantic import BaseModel

from pbe.judges.decisions import Choice, Noul, Question

DROPBOX_FOOTAGE = "Dropbox/Projects/Making Documentation/Print Build Eval/04 Test print footage"  # under the home folder


class Asked(BaseModel):
    """One question about a clip and the recorded answer: a choice option, or True/False for a noul."""
    id: str
    question: Question
    key: str | bool
    record: str  # the record's words the key comes from


class Clip(BaseModel):
    file: str        # name in the footage folder
    shows: str       # what the clip shows, as the request's text says it
    asked: list[Asked]

    @property
    def short(self) -> str:
        return self.file.split()[-1].split(".")[0]


BOLT_FIT = {
    "screwed": "The bolt only goes in by turning it, like a screw; its threads cut or grip the hole.",
    "pushed": "The bolt goes through when pushed, with some drag or grip, without turning.",
    "slid": "The bolt slides through freely or is loose in the hole.",
}


def _hole(n: int, bolt: str, key: str, record: str) -> Asked:
    ordinal = ("first", "second", "third")[n - 1]
    return Asked(id=f"hole_{n}", key=key, record=record, question=Choice(
        instructions=f"The {ordinal} hole the person tries the {bolt} in: how does the bolt go in?", criteria=BOLT_FIT))


def _goes_in(qid: str, which: str, key: bool, record: str) -> Asked:
    return Asked(id=qid, key=key, record=record, question=Noul(
        instructions=f"{which}: does the nut go into the pocket?",
        criteria={"true": "The nut goes in, by hand.", "false": "The nut doesn't go in, or only partly."}))


BOLTS_INTRO = "A 3D-printed test plate with a row of holes of slightly different sizes. A person tries a bolt in "
NUTS_INTRO = ("A 3D-printed test plate with hexagonal pockets for nuts, in two rows. A person tries to press a nut "
              "into each pocket with a thumb, first an M5 nut down one row, then down the other, then an M3 nut in "
              "the two smaller pockets.")

CLIPS = [
    Clip(file="round3-bolt-holes IMG_6162.MOV", shows=BOLTS_INTRO + "three of them, one after another: an M8 bolt.",
         asked=[_hole(1, "M8 bolt", "screwed", "screws in, but goes through"),
                _hole(2, "M8 bolt", "pushed", "goes through when pushed"),
                _hole(3, "M8 bolt", "slid", "slides through easily")]),
    Clip(file="round3-bolt-holes IMG_6163.MOV", shows=BOLTS_INTRO + "three of them, one after another: a 1/4-20 bolt.",
         asked=[_hole(1, "1/4-20 bolt", "screwed", "screws in only; gets really tight once through, but turns with a wrench"),
                _hole(2, "1/4-20 bolt", "pushed", "goes through with a bit of grip, not much"),
                _hole(3, "1/4-20 bolt", "slid", "loose")]),
    Clip(file="round3-nut-pockets IMG_6174.MOV", shows=NUTS_INTRO, asked=[
        _goes_in("row1_1", "The M5 nut in the first row, first pocket tried", False, "R2: doesn't go in"),
        _goes_in("row1_2", "The M5 nut in the first row, second pocket tried", False, "R1: doesn't go in"),
        _goes_in("row1_3", "The M5 nut in the first row, third pocket tried", False, "U3: doesn't really want to go in"),
        _goes_in("row2_1", "The M5 nut in the second row, first pocket tried", False, "L2: doesn't go in"),
        _goes_in("row2_2", "The M5 nut in the second row, second pocket tried", True, "L1: goes in nice and snug"),
        _goes_in("row2_3", "The M5 nut in the second row, third pocket tried", False, "Dan: 'third one doesn't really go in'"),
        _goes_in("row2_4", "The M5 nut in the second row, fourth pocket tried", False, "Dan: 'fourth one doesn't go in'"),
        _goes_in("row2_5", "The M5 nut in the second row, fifth pocket tried", False,
                 "R3: doesn't really go in, no matter how much I try"),
        _goes_in("m3_1", "The M3 nut in the first M3 pocket tried", False, "R5: M3 nut doesn't really go in"),
        _goes_in("m3_2", "The M3 nut in the second M3 pocket tried", False, "R4: M3 nut doesn't really go in either"),
    ]),
    Clip(file="round3-horn-pockets IMG_6186.MOV",
         shows="A 3D-printed test plate with three round pockets of slightly different sizes. A person sets a metal "
               "servo horn's hub into the pockets.",
         asked=[Asked(id="how_many_fit", key="one", record="2 are too big. one fits nicely", question=Choice(
                    instructions="In how many of the pockets does the horn's hub fit snugly, rather than loose?",
                    criteria={"none": "None of them.", "one": "Exactly one.", "two": "Exactly two.", "three": "All three."})),
                Asked(id="stays_tipped", key=True, record="the clip shows the horn staying in when the plate is "
                                                          "tipped on edge (the record's notes)", question=Noul(
                    instructions="When the plate is tipped up on its edge with the horn in a pocket, does the horn "
                                 "stay in?"))]),
    Clip(file="round3b-bridges-tested IMG_6158.MOV",
         shows="3D-printed test bridges: bars of plastic printed across gaps between blocks, with nothing under them "
               "while printing. A person handles and tests them.",
         asked=[Asked(id="strands_break", key=True, record="failed: all stringy, strings break", question=Noul(
                    instructions="Do strands of the printed bridges break or come loose when the person handles them?")),
                Asked(id="any_bridge_solid", key=False, record="i would say all of the bridges failed", question=Noul(
                    instructions="Does any of the bridges hold together as a solid bar, without loose or broken "
                                 "strands?"))]),
]
