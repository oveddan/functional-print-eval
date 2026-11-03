#!/usr/bin/env bash
# Build the image that run_python's code runs in (pbe/code_sandbox.py), from uv.lock.
# Run it once before a can_run_code run, and again whenever uv.lock changes: the runner
# refuses an image built from a different lock. BASE=... overrides the base image, e.g.
# BASE=mirror.gcr.io/library/python:3.12-slim@sha256:... when Docker Hub rate-limits.
# Any other arguments go to `docker build`, e.g. --network host --build-arg https_proxy=...
set -euo pipefail
cd "$(dirname "$0")/.."
engine="${PBE_CONTAINER_ENGINE:-docker}"
context="$(mktemp -d)"
trap 'rm -rf "$context"' EXIT
uv export --frozen --no-dev --no-emit-project --no-hashes --quiet -o "$context/requirements.txt"
lock_sha256="$(python3 -c 'import hashlib; print(hashlib.sha256(open("uv.lock", "rb").read()).hexdigest())')"
"$engine" build -t pbe-run-python --build-arg UV_LOCK_SHA256="$lock_sha256" ${BASE:+--build-arg BASE="$BASE"} \
    "$@" -f docker/run-python.Dockerfile "$context"
