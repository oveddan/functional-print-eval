# The image run_python's code runs in (pbe/code_sandbox.py). It holds the Python libraries
# from uv.lock and nothing of this repository: no pbe/, tasks/, results/ or catalog/.
# Built once, before a run; a trial never installs anything.
#
#   scripts/build_run_python_image.sh
#
# The runner refuses an image built from a different uv.lock (the label below).
ARG BASE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30
FROM ${BASE}

# what CadQuery's OpenCascade and VTK wheels load, and fonts for text on a part
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxrender1 libxext6 libx11-6 libfontconfig1 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.txt && rm /tmp/requirements.txt

ARG UV_LOCK_SHA256=unknown
LABEL pbe.uv_lock_sha256=${UV_LOCK_SHA256}

# no network, no environment, a non-root user, the trial's folder at /work: all set by `docker run`
ENV HOME=/tmp MPLCONFIGDIR=/tmp
WORKDIR /work
