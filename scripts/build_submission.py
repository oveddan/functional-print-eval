"""Build the hackathon submission ZIP from a git ref, and refuse to finish unless it's safe to hand in.

    uv run python scripts/build_submission.py main
    uv run python scripts/build_submission.py main --out ../print-build-eval.zip

Only files tracked at the ref go in (so no .git, no local results, nothing untracked), less the paths in
LEFT_OUT. The ZIP is written outside the repo, with README.md at its root. It isn't written at all, and the
script exits 1 listing every reason, if the ZIP would be 50 MB or more, has no README.md at its root, or
holds a video, `docs/context/`, `.git`, a secret, or a machine-local path (a home folder, a LAN or tailnet
address). Image metadata isn't checked (Dan, 2026-11-04: EXIF is fine). tests/test_build_submission.py has a
test for each refusal.
"""
import argparse
import io
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIMIT_BYTES = 50_000_000  # the hackathon's 50 MB, read as decimal megabytes, the stricter reading

# Tracked files that don't ship, each with why. The overnight logs are Dan's call (issue 36); until he
# decides, they stay out, and docs/overnight-runs.md has the home network in it.
LEFT_OUT = {
    "docs/context/": "private source material (CLAUDE.md)",
    "docs/overnight-runs.md": "names the home LAN and tailnet setup; whether the overnight logs ship is Dan's call (issue 36)",
    "docs/overnight-2026-11-02-log.md": "a working log; whether the overnight logs ship is Dan's call (issue 36)",
    "report/atlas/": "the failure atlas builds only on Dan's Mac, from photos its examples.yaml finds on that machine (issue 6)",
    "tasks/estoa-light/files/datasheet.png": "the vendor's drawing: estoa-public doesn't ship it either, so fetch it from Adafruit (product 2477) at setup (issue 6)",
}

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".mpg", ".mpeg", ".3gp"}

# A match a few characters into a long base64 blob is chance, so a secret has to start at a word boundary.
SECRETS = {
    "an OpenAI, OpenRouter or Anthropic style API key": r"(?<![\w-])sk-(?:or-|ant-)?[A-Za-z0-9_-]{20,}",
    "an AWS access key": r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])",
    "a GitHub token": r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "a private key": r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
    "a bearer token": r"(?<!\w)Bearer [A-Za-z0-9._~+/-]{20,}=*",
}
OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
MACHINE_LOCAL = {
    "a macOS home folder": r"/Users/[\w.-]+",
    "a Linux home folder": r"/home/[a-z][\w.-]*/",
    "a path in someone's home folder": r"(?<![\w.~])~/[\w.-]",
    "a LAN address": rf"(?<![\d.])(?:10\.{OCTET}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.{OCTET}\.{OCTET}(?![\d.])",
    "a tailnet address": rf"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.{OCTET}\.{OCTET}(?![\d.])|[\w-]+\.ts\.net\b",
}


@dataclass(frozen=True)
class Entry:
    """One file as it would go in the ZIP."""
    path: str
    data: bytes


@dataclass(frozen=True)
class Refusal:
    """One reason the ZIP can't be handed in. `line` is 1-based, or 0 for the whole file."""
    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path or "(the ZIP)"
        return f"{where}: {self.reason}"


def left_out_reason(path: str) -> str | None:
    for prefix, why in LEFT_OUT.items():
        if path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
            return why
    return None


def tracked_entries(ref: str) -> list[Entry]:
    """Every file tracked at `ref`, read from git rather than the working tree."""
    archive = subprocess.run(["git", "archive", "--format=tar", ref], cwd=ROOT, capture_output=True, check=True).stdout
    entries = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                entries.append(Entry(member.name, tar.extractfile(member).read()))
    return entries


def path_refusals(entry: Entry) -> list[Refusal]:
    parts = Path(entry.path).parts
    found = []
    if Path(entry.path).suffix.lower() in VIDEO_SUFFIXES:
        found.append(Refusal(entry.path, 0, "a video"))
    if ".git" in parts:
        found.append(Refusal(entry.path, 0, "part of .git"))
    if entry.path.startswith("docs/context/"):
        found.append(Refusal(entry.path, 0, "private source material in docs/context/"))
    return found


def as_text(data: bytes) -> str | None:
    """The file as text, or None if it's binary."""
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def text_refusals(entry: Entry) -> list[Refusal]:
    """Secrets and machine-local paths, by line. Binary files aren't read."""
    text = as_text(entry.data)
    if text is None:
        return []
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for what, pattern in {**SECRETS, **MACHINE_LOCAL}.items():
            if re.search(pattern, line):
                found.append(Refusal(entry.path, number, what))
    return found


def contents_refusals(entries: list[Entry]) -> list[Refusal]:
    found = []
    if not any(entry.path == "README.md" for entry in entries):
        found.append(Refusal("README.md", 0, "no README.md at the ZIP's root"))
    for entry in entries:
        found += path_refusals(entry) + text_refusals(entry)
    return found


def zip_bytes(entries: list[Entry]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in sorted(entries, key=lambda entry: entry.path):
            archive.writestr(entry.path, entry.data)
    return buffer.getvalue()


def size_refusals(data: bytes) -> list[Refusal]:
    if len(data) >= LIMIT_BYTES:
        return [Refusal("", 0, f"{len(data) / 1e6:.1f} MB, not under {LIMIT_BYTES / 1e6:.0f} MB")]
    return []


def out_refusals(out: Path) -> list[Refusal]:
    if out.resolve().is_relative_to(ROOT):
        return [Refusal(str(out), 0, "the ZIP has to be written outside the repo")]
    return []


def default_out(ref: str) -> Path:
    commit = subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return ROOT.parent / f"print-build-eval-{commit}.zip"


def build(ref: str, out: Path) -> list[Refusal]:
    """Write the ZIP to `out` and return no refusals, or write nothing and return every refusal."""
    refusals = out_refusals(out)
    entries = [entry for entry in tracked_entries(ref) if left_out_reason(entry.path) is None]
    refusals += contents_refusals(entries)
    data = zip_bytes(entries)
    refusals += size_refusals(data)
    if not refusals:
        out.write_bytes(data)
    return refusals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ref", help="the git ref to package, e.g. main")
    parser.add_argument("--out", type=Path, help="where to write the ZIP; default: beside the repo, named by commit")
    args = parser.parse_args()
    out = (args.out or default_out(args.ref)).expanduser()
    refusals = build(args.ref, out)
    if refusals:
        print(f"Not written: {len(refusals)} reason(s) the ZIP can't be handed in:", file=sys.stderr)
        for refusal in refusals:
            print(f"  {refusal}", file=sys.stderr)
        sys.exit(1)
    print(f"{out}: {out.stat().st_size / 1e6:.1f} MB, from {args.ref}")
    for prefix, why in LEFT_OUT.items():
        print(f"  left out {prefix}: {why}")


if __name__ == "__main__":
    main()
