#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv-build
.venv-build/bin/python -m pip install -r desktop/requirements-build.txt
exec .venv-build/bin/python scripts/build-desktop.py "$@"
