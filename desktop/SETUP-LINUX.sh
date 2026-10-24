#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required")'
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
requirements_file=requirements.txt
if [[ -f requirements-release.txt ]]; then
  requirements_file=requirements-release.txt
fi
.venv/bin/python -m pip install -r "$requirements_file"
printf '%s\n' 'Setup complete. Run: bash START-LINUX.sh'
