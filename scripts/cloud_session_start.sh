#!/bin/bash
# Installs the project's dependencies in a cloud session. Does nothing anywhere else.
[ "$CLAUDE_CODE_REMOTE" = "true" ] || exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 1
uv sync --frozen --quiet
