"""Builds CHANGELOG.md from the change files in changes/, one file per change.

Every PR used to add its entry to the top of CHANGELOG.md, so any two open PRs conflicted there
on every rebase. Now each PR adds its own file, changes/<YYYY-MM-DD>-<slug>.md, starting with
"## <YYYY-MM-DD>: <what changed>" and followed by the entry: what changed, why, and the evidence.
No two PRs touch the same file. CHANGELOG.md is git-ignored and built on demand: the newest
change files first, then changes/history.md, the entries written before change files existed.

    uv run python scripts/changelog.py              # print the changelog
    uv run python scripts/changelog.py --write      # write CHANGELOG.md
    uv run python scripts/changelog.py --check      # every change file is well formed
    uv run python scripts/changelog.py --check --pr-base origin/main
        # ...and a branch that changes results/, pbe/graders/ or catalog/ adds a change file
"""
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGES = ROOT / "changes"
CHANGELOG = ROOT / "CHANGELOG.md"
HISTORY = "history.md"
README = "README.md"

HEADER = """# Changelog

Each entry: what changed, why, and the evidence (a run, a failure, a measurement).

Built from `changes/` by `scripts/changelog.py`: add a change file there rather than editing this file.

"""

FILE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9-]*\.md$")

# A change under these paths can move a grade, so its PR must add a change file.
NEEDS_ENTRY = ("results/", "pbe/graders/", "catalog/")


@dataclass(frozen=True)
class Entry:
    path: Path
    day: date
    text: str


class BadChangeFile(ValueError):
    pass


def file_date(path: Path) -> date:
    """The date in a change file's name, or BadChangeFile if the name isn't <YYYY-MM-DD>-<slug>.md."""
    match = FILE_NAME.match(path.name)
    if not match:
        raise BadChangeFile(f"{path.name}: name it <YYYY-MM-DD>-<slug>.md (lower case, digits and dashes)")
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        raise BadChangeFile(f"{path.name}: {match.group(1)} isn't a date") from None


def read_entry(path: Path) -> Entry:
    """One change file, checked: its first line is "## <the file's date>: <what changed>"."""
    day = file_date(path)
    text = path.read_text()
    heading = text.split("\n", 1)[0]
    prefix = f"## {day.isoformat()}: "
    if not heading.startswith(prefix) or not heading[len(prefix):].strip():
        raise BadChangeFile(f"{path.name}: the first line must be \"{prefix}<what changed>\", not {heading!r}")
    if not text[len(heading):].strip():
        raise BadChangeFile(f"{path.name}: the entry has a heading but nothing under it")
    return Entry(path, day, text)


def change_files(directory: Path) -> list[Path]:
    """Every file in changes/ except the history and the folder's README."""
    return [path for path in sorted(directory.iterdir()) if path.name not in (HISTORY, README)]


def problems(directory: Path) -> list[str]:
    """What's wrong with each change file; empty when they're all well formed."""
    found = []
    for path in change_files(directory):
        try:
            read_entry(path)
        except BadChangeFile as error:
            found.append(str(error))
    return found


def entries(directory: Path) -> list[Entry]:
    """The change files, newest first; a day's entries in reverse order of name."""
    read = [read_entry(path) for path in change_files(directory)]
    return sorted(read, key=lambda entry: (entry.day, entry.path.name), reverse=True)


def changelog(directory: Path) -> str:
    """The whole changelog: the header, the change files newest first, then the history."""
    newest = "".join(entry.text.rstrip("\n") + "\n\n" for entry in entries(directory))
    return HEADER + newest + (directory / HISTORY).read_text()


def needs_entry(changed: list[str]) -> bool:
    return any(path.startswith(NEEDS_ENTRY) for path in changed)


def is_change_file(path: str) -> bool:
    return path.startswith("changes/") and FILE_NAME.match(path.removeprefix("changes/")) is not None


def missing_entry(changed: list[str], added: list[str]) -> bool:
    """A branch that changes what's graded but adds no change file."""
    return needs_entry(changed) and not any(is_change_file(path) for path in added)


def git_paths(root: Path, base: str, *options: str) -> list[str]:
    """Paths this branch changed since it left base; renames count as a delete and an add."""
    result = subprocess.run(["git", "diff", "--name-only", "--no-renames", *options, f"{base}...HEAD"],
                            cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.split()


def check_branch(base: str, root: Path = ROOT) -> list[str]:
    """Why this branch, compared with base, still needs a change file; empty when it doesn't."""
    changed = git_paths(root, base)
    if not missing_entry(changed, git_paths(root, base, "--diff-filter=A")):
        return []
    graded = [path for path in changed if path.startswith(NEEDS_ENTRY)]
    shown = ", ".join(graded[:5]) + (f" and {len(graded) - 5} more" if len(graded) > 5 else "")
    return [f"this branch changes {shown} but adds no change file: add changes/<YYYY-MM-DD>-<slug>.md "
            "(see changes/README.md); if no result moved, the entry says so and why"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="write CHANGELOG.md")
    parser.add_argument("--check", action="store_true", help="fail if a change file is badly formed")
    parser.add_argument("--pr-base", help="with --check: also fail if this branch changes results/, "
                                          "pbe/graders/ or catalog/ without adding a change file")
    args = parser.parse_args()
    if args.check:
        found = problems(CHANGES) + (check_branch(args.pr_base) if args.pr_base else [])
        for problem in found:
            print(f"error: {problem}", file=sys.stderr)
        return 1 if found else 0
    text = changelog(CHANGES)
    if args.write:
        CHANGELOG.write_text(text)
        print(f"wrote {CHANGELOG.relative_to(ROOT)}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
