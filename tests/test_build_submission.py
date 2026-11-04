"""The submission ZIP refuses every kind of file that mustn't be handed in, and today's tree passes."""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_submission as zipper  # noqa: E402

README = zipper.Entry("README.md", b"# Print-and-Build Eval\n")


def reasons(*entries):
    return [refusal.reason for refusal in zipper.contents_refusals([README, *entries])]


def test_a_clean_tree_has_nothing_to_refuse():
    assert reasons(zipper.Entry("pbe/eval.py", b"print('hello')\n")) == []


def test_no_readme_at_the_root():
    found = zipper.contents_refusals([zipper.Entry("docs/README.md", b"# not at the root\n")])
    assert [refusal.reason for refusal in found] == ["no README.md at the ZIP's root"]


@pytest.mark.parametrize("path", ["docs/demo.mp4", "clips/take1.MOV", "a.webm"])
def test_a_video(path):
    assert reasons(zipper.Entry(path, b"\0\0\0 ftyp")) == ["a video"]


def test_part_of_git():
    assert reasons(zipper.Entry(".git/config", b"[core]\n")) == ["part of .git"]


def test_private_source_material():
    assert reasons(zipper.Entry("docs/context/INDEX.md", b"notes\n")) == ["private source material in docs/context/"]


@pytest.mark.parametrize("line, what", [
    ("key = 'sk-or-v1-" + "a1b2c3d4" * 8 + "'", "an OpenAI, OpenRouter or Anthropic style API key"),
    ("ANTHROPIC=sk-ant-api03-" + "x" * 40, "an OpenAI, OpenRouter or Anthropic style API key"),
    ("aws_access_key_id = AKIA" + "ABCDEFGHIJKLMNOP", "an AWS access key"),
    ("token: ghp_" + "a" * 36, "a GitHub token"),
    ("-----BEGIN OPENSSH " + "PRIVATE KEY-----", "a private key"),
    ("Authorization: Bearer " + "eyJhbGciOiJIUzI1NiJ9" + "abc" * 5, "a bearer token"),
])
def test_a_secret(line, what):
    found = zipper.contents_refusals([README, zipper.Entry("notes.md", f"fine\n{line}\n".encode())])
    assert [(refusal.line, refusal.reason) for refusal in found] == [(2, what)]


# each example is split in two, so this file doesn't trip the sweep it tests
@pytest.mark.parametrize("line, what", [
    ("see /Users/" + "someone/Desktop/plate.scad", "a macOS home folder"),
    ("see /home/" + "someone/plate.scad", "a Linux home folder"),
    ("photo in ~/" + "Downloads/IMG_1.HEIC", "a path in someone's home folder"),
    ("design in ~/" + "Source/private/plate.scad", "a path in someone's home folder"),
    ("ssh pbe@192.168." + "4.10", "a LAN address"),
    ("server at 10.0." + "0.12", "a LAN address"),
    ("nas at 172.20." + "1.5", "a LAN address"),
    ("tailnet 100.101." + "102.103", "a tailnet address"),
    ("box.tail1234" + ".ts.net", "a tailnet address"),
])
def test_a_machine_local_path(line, what):
    assert reasons(zipper.Entry("PLAN.md", line.encode())) == [what]


@pytest.mark.parametrize("line", [
    "version 10.2.3",                       # three numbers, not an address
    "gAAAAABmskdl-sk-" + "a" * 40,          # 'sk-' inside an encrypted blob is chance, not a key
    "f\"Bearer {_key()}\"",                 # the code that sends the key, not a key
    "an M5 bolt, 172.5 mm",
])
def test_lookalikes_pass(line):
    assert reasons(zipper.Entry("notes.md", line.encode())) == []


def test_binary_files_arent_read_as_text():
    assert reasons(zipper.Entry("docs/media/x.png", b"\x89PNG\r\n\x1a\n\0 /Users/" + b"x ~/" + b"Downloads")) == []


def test_too_big(monkeypatch):
    monkeypatch.setattr(zipper, "LIMIT_BYTES", 10)
    assert [refusal.reason for refusal in zipper.size_refusals(b"x" * 10)] == ["0.0 MB, not under 0 MB"]
    assert zipper.size_refusals(b"x" * 9) == []


def test_written_inside_the_repo():
    assert [r.reason for r in zipper.out_refusals(zipper.ROOT / "out.zip")] == ["the ZIP has to be written outside the repo"]


def test_what_is_left_out():
    assert zipper.left_out_reason("docs/context/INDEX.md")
    assert zipper.left_out_reason("report/atlas/examples.yaml")
    assert zipper.left_out_reason("docs/overnight-runs.md")
    assert zipper.left_out_reason("tasks/estoa-light/files/datasheet.png")
    assert zipper.left_out_reason("docs/limitations.md") is None


def test_this_commit_builds_a_zip_that_can_be_handed_in(tmp_path):
    out = tmp_path / "submission.zip"
    assert [str(refusal) for refusal in zipper.build("HEAD", out)] == []
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
    assert "README.md" in names
    assert not any(name.startswith(("docs/context/", ".git/", "report/atlas/")) for name in names)
    assert out.stat().st_size < zipper.LIMIT_BYTES
