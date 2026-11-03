"""Look up hardware in catalog/hardware.yaml by a short reference string."""
import re
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@cache
def _data():
    return yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())


def _family(kind, standard):
    for fam in _data()[kind]:
        if fam["standard"].split(" (")[0] == standard:
            return fam
    raise KeyError(f"no {kind} to {standard}")


def resolve(ref: str) -> dict:
    """Dimensions for a reference such as "ISO 4762 M5x30", "ISO 4032 M5",
    "ISO 7089 M5", "insert M3x4x5", "608ZZ" or "salvaged:webcam-mount-bolt"."""
    if ref.startswith("salvaged:"):
        key = ref.split(":", 1)[1]
        for item in _data()["salvaged"]:
            if item["id"] == key:
                return {"kind": "salvaged", **item}
        raise KeyError(f"no salvaged part {key}")
    for item in _data()["bearings"]:
        if ref in (item["id"], item["id"].removesuffix("ZZ")):
            return {"kind": "bearing", **item}
    if ref.startswith("insert "):
        size = ref.split(" ", 1)[1]
        return {"kind": "insert", "size": size, **_family("inserts", "none")["sizes"][size]}
    m = re.fullmatch(r"(ISO \d+|ASME B18\.2\.2) (M\d+|1/4-20)(?:x(\d+))?", ref)
    if not m:
        raise KeyError(f"can't read hardware reference {ref!r}")
    standard, size, length = m.group(1), m.group(2), m.group(3)
    for kind in ("screws", "nuts", "washers"):
        try:
            fam = _family(kind, standard)
        except KeyError:
            continue
        dims = dict(fam["sizes"][size])
        out = {"kind": kind[:-1], "standard": standard, "size": size, "pitch": _data()["pitch_mm"][size], **dims}
        if kind == "screws":
            if not length:
                raise KeyError(f"screw {ref!r} needs a length, e.g. {standard} {size}x20")
            length = int(length)
            out["length"] = length
            # ISO 4762: threaded close to the head up to a cut-off length, else b of thread
            out["thread_length"] = length if length <= dims["threaded_to_head_max"] else dims["b"]
        return out
    raise KeyError(f"no hardware to {standard}")
