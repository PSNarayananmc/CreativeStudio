#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec "${CREATIVE_STUDIO_PYTHON:-python3}" main.py "$@"
