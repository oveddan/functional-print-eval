"""The results site's committed 3D files and failure drawings follow the saved findings: a design whose findings
changed is out of date, a partial run keeps every other design, and replaced drawings lose their audit answers.
Temporary run folders and manifests only; nothing is drawn or uploaded."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import results_site  # noqa: E402
import results_site_media as media  # noqa: E402
import results_site_views as views  # noqa: E402

FAILED_R2 = {"check": "R2", "part": "-", "ok": False, "detail": "40.0 mm wide", "test_print": False}
PASSED_R2 = {"check": "R2", "part": "-", "ok": True, "detail": "38.0 mm wide", "test_print": False}


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Point both scripts and the site's audit at a temporary results/runs and temporary manifests."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(media, "RUNS", runs)
    monkeypatch.setattr(media, "MANIFEST", tmp_path / "media.json")
    monkeypatch.setattr(media, "RECORDS", tmp_path / "media-records")
    monkeypatch.setattr(views, "COMMITTED", tmp_path / "views.json")
    monkeypatch.setattr(views, "RECORDS", tmp_path / "view-records")
    monkeypatch.setattr(results_site, "VIEW_AUDIT", tmp_path / "audit.json")
    results_site.view_audit.cache_clear()
    yield runs
    results_site.view_audit.cache_clear()


def design(runs, name, findings, declined=False, extra=None):
    folder = runs / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "submission.yaml").write_text("task: tripod-plate\nparts: []\n")
    (folder / "grades.json").write_text(json.dumps({"findings": findings, "declined": declined, **(extra or {})}))
    return folder


def view_record(folder, findings, obj):
    """A views record as process() saves one, with the content key work() gives it."""
    return {"rel": media.rel(folder), "version": views.VERSION, "key": media.content_key(folder, views.VERSION),
            "failed_only": False,
            "views": [{"check": f["check"], "part": f["part"], "state": "fail", "test_print": False, "kind": "plan",
                       "caption": f["detail"], "object": obj, "no_view_reason": None}
                      for f in findings]}


def committed_views(designs, keys):
    return json.dumps({"version": views.VERSION, "designs": designs, "keys": keys})


def drawn(check, url):
    return {"check": check, "part": "-", "state": "fail", "test_print": False, "kind": "plan", "caption": "",
            "view": url, "no_view_reason": None, "width": 10, "height": 10}


def test_the_key_follows_the_findings_but_not_the_rest_of_a_regrade(site):
    folder = design(site, "run/t1", [FAILED_R2])
    before = media.content_key(folder, 1)
    design(site, "run/t1", [FAILED_R2], extra={"regrades": [{"date": "2026-11-14"}], "date": "2026-11-14"})
    assert media.content_key(folder, 1) == before
    design(site, "run/t1", [PASSED_R2])
    assert media.content_key(folder, 1) != before
    assert media.content_key(folder, 2) != media.content_key(folder, 1)


def test_a_saved_record_is_reused_only_while_its_key_is_current(site, monkeypatch):
    folder = design(site, "run/t1", [FAILED_R2])
    made = []
    monkeypatch.setattr(media, "process", lambda f: made.append(f) or {"rel": media.rel(f), "version": media.VERSION,
                                                                     "built": True, "error": None, "parts": [], "scene": None})
    media.work(folder)
    media.work(folder)
    assert len(made) == 1
    design(site, "run/t1", [PASSED_R2])
    media.work(folder)
    assert len(made) == 2
    media.work(folder, force=True)  # --all redoes a design even while its record is current
    assert len(made) == 3


def test_writing_the_media_manifest_keeps_other_designs_and_drops_removed_ones(site):
    kept, redone = design(site, "run/kept", [FAILED_R2]), design(site, "run/redone", [FAILED_R2])
    media.MANIFEST.write_text(json.dumps({"designs": {"run/kept": {"built": True}, "run/redone": {"built": True},
                                                      "run/gone": {"built": True}},
                                          "keys": {"run/kept": "k", "run/redone": "old", "run/gone": "g"}}))
    record = {"rel": "run/redone", "built": False, "error": "no parts", "parts": [], "scene": None,
              "key": media.content_key(redone, media.VERSION)}
    media.write_manifest([record])
    saved = json.loads(media.MANIFEST.read_text())
    assert set(saved["designs"]) == {"run/kept", "run/redone"} and saved["designs"]["run/kept"] == {"built": True}
    assert saved["keys"] == {"run/kept": "k", "run/redone": record["key"]}
    assert media.stale([kept, redone]) == [kept]


def test_check_flags_a_design_whose_findings_changed_but_not_a_declined_one(site):
    current = design(site, "run/current", [FAILED_R2])
    changed = design(site, "run/changed", [FAILED_R2])
    declined = design(site, "run/declined", [FAILED_R2], declined=True)
    keys = {"run/current": media.content_key(current, views.VERSION), "run/changed": media.content_key(changed, views.VERSION)}
    views.COMMITTED.write_text(committed_views({"run/current": [drawn("R2", "https://m/a.webp")],
                                                "run/changed": [drawn("R2", "https://m/b.webp")]}, keys))
    design(site, "run/changed", [FAILED_R2 | {"detail": "41.0 mm wide"}])
    assert views.stale([current, changed, declined]) == [changed]
    assert views.check([current, declined]) == 0
    assert views.check([current, changed, declined]) == 1


def test_writing_the_drawings_overlays_and_prunes_the_audit(site, monkeypatch):
    kept = design(site, "run/kept", [FAILED_R2])
    redrawn = design(site, "run/redrawn", [FAILED_R2])
    emptied = design(site, "run/emptied", [PASSED_R2])  # its check passes now: nothing left to draw
    views.COMMITTED.write_text(committed_views(
        {"run/kept": [drawn("R2", "https://m/kept.webp")], "run/redrawn": [drawn("R2", "https://m/old.webp")],
         "run/emptied": [drawn("R2", "https://m/emptied.webp")], "run/gone": [drawn("R2", "https://m/gone.webp")]},
        {"run/kept": media.content_key(kept, views.VERSION), "run/redrawn": "old", "run/emptied": "old", "run/gone": "g"}))
    audit = {url: {"shows_failure": True, "p": 0.9, "model": "m"}
             for url in ("https://m/kept.webp", "https://m/old.webp", "https://m/emptied.webp", "https://m/gone.webp")}
    results_site.VIEW_AUDIT.write_text(json.dumps({"views": audit}))
    monkeypatch.setattr(views, "view_ref", lambda obj, uploaded: obj)
    new = view_record(redrawn, [FAILED_R2], "https://m/new.webp")
    nothing = {"rel": "run/emptied", "version": views.VERSION, "key": media.content_key(emptied, views.VERSION),
               "failed_only": False, "views": []}
    monkeypatch.setattr(views, "pixel_size", lambda obj: (10, 10))
    views.write_committed([new, nothing], set())
    saved = json.loads(views.COMMITTED.read_text())
    assert set(saved["designs"]) == {"run/kept", "run/redrawn"}
    assert saved["designs"]["run/kept"][0]["view"] == "https://m/kept.webp"
    assert saved["designs"]["run/redrawn"][0]["view"] == "https://m/new.webp"
    assert set(saved["keys"]) == {"run/kept", "run/redrawn", "run/emptied"}
    assert set(json.loads(results_site.VIEW_AUDIT.read_text())["views"]) == {"https://m/kept.webp"}
    assert views.check([kept, redrawn, emptied]) == 0


def test_the_committed_site_files_are_current():
    """The real manifests were made from today's saved findings: a regrade that leaves the site behind fails here,
    in CI, with the command that fixes it (scripts/results_site_media.py, then scripts/results_site_views.py)."""
    folders = media.design_folders()
    assert media.stale(folders) == []
    assert views.check(folders) == 0


def test_a_failed_only_run_never_becomes_a_committed_entry(site, monkeypatch):
    folder = design(site, "run/t1", [FAILED_R2, {"check": "R4", "part": "-", "ok": None, "detail": "not graded", "test_print": False}])
    views.COMMITTED.write_text(committed_views({}, {}))
    partial = view_record(folder, [FAILED_R2], None) | {"failed_only": True}
    views.write_committed([partial], set())
    assert views.stale([folder]) == [folder]
