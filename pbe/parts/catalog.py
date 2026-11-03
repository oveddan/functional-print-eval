"""Look up hardware in catalog/hardware.yaml by a short reference string."""
import re
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


@cache
def _data():
    return yaml.safe_load((ROOT / "catalog/hardware.yaml").read_text())


def _family(kind, standard):
    for family in _data()[kind]:
        if family["standard"].split(" (")[0] == standard:
            return family
    raise KeyError(f"no {kind} to {standard}")


def _salvaged(key):
    for item in _data()["salvaged"]:
        if item["id"] == key:
            return {"kind": "salvaged", **item}
    raise KeyError(f"no salvaged part {key}")


def _bearing(ref):
    """The bearing named by `ref`, with or without its ZZ, or None."""
    for item in _data()["bearings"]:
        if ref in (item["id"], item["id"].removesuffix("ZZ")):
            return {"kind": "bearing", **item}
    return None


def _standard_part(ref, standard, size, length):
    """A screw, nut or washer to an ISO or ASME standard."""
    for kind in ("screws", "nuts", "washers"):
        try:
            family = _family(kind, standard)
        except KeyError:
            continue
        dims = dict(family["sizes"][size])
        part = {"kind": kind[:-1], "standard": standard, "size": size, "pitch": _data()["pitch_mm"][size], **dims}
        if kind != "screws":
            return part
        if not length:
            raise KeyError(f"screw {ref!r} needs a length, e.g. {standard} {size}x20")
        part["length"] = int(length)
        # ISO 4762: threaded close to the head up to a cut-off length, else b of thread
        part["thread_length"] = part["length"] if part["length"] <= dims["threaded_to_head_max"] else dims["b"]
        return part
    raise KeyError(f"no hardware to {standard}")


def resolve(ref: str) -> dict:
    """Dimensions for a reference such as "ISO 4762 M5x30", "ISO 4032 M5",
    "ISO 7089 M5", "insert M3x4x5", "608ZZ" or "salvaged:webcam-mount-bolt"."""
    if ref.startswith("salvaged:"):
        return _salvaged(ref.split(":", 1)[1])
    if bearing := _bearing(ref):
        return bearing
    if ref.startswith("insert "):
        size = ref.split(" ", 1)[1]
        return {"kind": "insert", "size": size, **_family("inserts", "none")["sizes"][size]}
    match = re.fullmatch(r"(ISO \d+|ASME B18\.2\.2) (M\d+|1/4-20)(?:x(\d+))?", ref)
    if not match:
        raise KeyError(f"can't read hardware reference {ref!r}")
    standard, size, length = match.groups()
    return _standard_part(ref, standard, size, length)
