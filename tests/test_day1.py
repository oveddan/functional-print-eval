from pathlib import Path

import pytest
from pydantic import ValidationError

from pbe import catalog, checks, submission
from pbe.build import build_parts

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/arca-plate"


def test_catalog_partial_thread():
    # the tripod's phone clamp screw: an M5x50 has only b = 22 mm of thread
    assert catalog.resolve("ISO 4762 M5x50")["thread_length"] == 22
    assert catalog.resolve("ISO 4762 M5x20")["thread_length"] == 20
    assert catalog.resolve("ISO 4032 M5")["af"] == 8.0


def test_catalog_salvaged_has_no_dimensions():
    bolt = catalog.resolve("salvaged:webcam-mount-bolt")
    assert bolt["head_d"] is None and bolt["thread"] == "1/4-20"


def test_catalog_rejects_unknown():
    with pytest.raises(KeyError):
        catalog.resolve("ISO 4762 M7x20")
    with pytest.raises(KeyError):
        catalog.resolve("ISO 4762 M5")  # a screw needs a length


def test_submission_rejects_dangling_references():
    sub = submission.load(EXAMPLES / "original.yaml").model_dump()
    sub["joints"][0]["seats"][0]["part"] = "no-such-part"
    with pytest.raises(ValidationError, match="unknown part no-such-part"):
        submission.Submission.model_validate(sub)


@pytest.mark.parametrize("name, recess_d, roof_ok", [("original", 13, False), ("fix", 15, True)])
def test_arca_backtest(tmp_path, name, recess_d, roof_ok):
    # the original's roof printed as a tangle; the fix's stepped roof printed clean
    sub = submission.load(EXAMPLES / f"{name}.yaml")
    assert sub.params["recess_d"].value == recess_d
    built = build_parts(sub, tmp_path)
    assert built["plate"].mesh.is_watertight
    findings = {f.check: f for check in checks.ALL for f in check(built)}
    assert findings["builds"].ok and findings["connected_bodies"].ok and findings["bed_fit"].ok
    assert findings["bridges"].ok is roof_ok, findings["bridges"].detail


def test_arca_overrides_change_geometry(tmp_path):
    # the metamorphic check depends on params actually driving the geometry
    sub = submission.load(EXAMPLES / "original.yaml")
    small = build_parts(sub, tmp_path / "a")["plate"].mesh.volume
    big = build_parts(sub, tmp_path / "b", overrides={"recess_d": 16})["plate"].mesh.volume
    assert big < small
