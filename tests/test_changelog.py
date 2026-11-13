"""The changelog is built from one change file per PR, and CI insists on one where grades can move."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import changelog  # noqa: E402

HISTORY = "## 2026-11-01: The oldest entry\n\n- Before change files.\n"


def folder(tmp_path: Path, files: dict[str, str]) -> Path:
    """A changes/ folder holding these files and a history."""
    (tmp_path / changelog.HISTORY).write_text(HISTORY)
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    return tmp_path


def entry(day: str, title: str) -> str:
    return f"## {day}: {title}\n\n- What changed, and the evidence.\n"


def test_the_repos_change_files_are_well_formed():
    assert changelog.problems(changelog.CHANGES) == [], "fix the change files named above"


def test_the_changelog_is_the_header_then_newest_first_then_the_history(tmp_path):
    changes = folder(tmp_path, {
        "2026-11-12-older.md": entry("2026-11-12", "Older"),
        "2026-11-13-newer.md": entry("2026-11-13", "Newer"),
        "README.md": "# Not an entry\n",
    })
    text = changelog.changelog(changes)
    assert text.startswith(changelog.HEADER)
    assert text.endswith(HISTORY)
    assert text.index("Newer") < text.index("Older") < text.index("The oldest entry")
    assert "Not an entry" not in text
    assert "\n\n\n" not in text


def test_an_entry_with_no_trailing_newline_is_still_followed_by_a_blank_line(tmp_path):
    changes = folder(tmp_path, {"2026-11-13-a.md": "## 2026-11-13: A\n\n- body"})
    assert "- body\n\n## 2026-11-01: The oldest entry" in changelog.changelog(changes)


@pytest.mark.parametrize("name, text, complaint", [
    ("2026-11-13 servo fix.md", entry("2026-11-13", "x"), "name it"),
    ("servo-fix.md", entry("2026-11-13", "x"), "name it"),
    ("2026-13-01-servo.md", entry("2026-13-01", "x"), "isn't a date"),
    ("2026-11-13-servo.md", entry("2026-11-12", "x"), "first line"),
    ("2026-11-13-servo.md", "# 2026-11-13: x\n\n- body\n", "first line"),
    ("2026-11-13-servo.md", "## 2026-11-13: \n\n- body\n", "first line"),
    ("2026-11-13-servo.md", "## 2026-11-13: A title\n\n", "nothing under it"),
])
def test_a_badly_formed_change_file_is_named_with_what_to_fix(tmp_path, name, text, complaint):
    found = changelog.problems(folder(tmp_path, {name: text}))
    assert len(found) == 1 and name in found[0] and complaint in found[0]


@pytest.mark.parametrize("changed, added, missing", [
    (["pbe/graders/servo.py"], [], True),
    (["results/runs/x/grades.json"], [], True),
    (["catalog/hardware.yaml", "changes/2026-11-13-x.md"], ["changes/2026-11-13-x.md"], False),
    (["README.md", "scripts/digest.py"], [], False),
    # editing someone else's entry, or the history, isn't this change's entry
    (["pbe/graders/servo.py", "changes/2026-11-12-y.md"], [], True),
    (["pbe/graders/servo.py"], ["changes/history.md"], True),
    (["pbe/graders/servo.py"], ["changes/notes.txt"], True),
    # pbe/ outside the graders doesn't need one
    (["pbe/runner/agent.py"], [], False),
])
def test_ci_wants_a_change_file_where_grades_can_move(changed, added, missing):
    assert changelog.missing_entry(changed, added) is missing


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


def test_ci_reads_the_branch_from_git(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pbe" / "graders").mkdir(parents=True)
    (tmp_path / "pbe" / "graders" / "servo.py").write_text("LIMIT = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "fix")
    (tmp_path / "pbe" / "graders" / "servo.py").write_text("LIMIT = 2\n")
    git(tmp_path, "commit", "-q", "-am", "grader change, no entry")
    assert "pbe/graders/servo.py" in changelog.check_branch("main", tmp_path)[0]
    (tmp_path / "changes").mkdir()
    (tmp_path / "changes" / "2026-11-13-servo-limit.md").write_text(entry("2026-11-13", "Servo limit"))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "entry")
    assert changelog.check_branch("main", tmp_path) == []
