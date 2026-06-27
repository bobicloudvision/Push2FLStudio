#!/usr/bin/env bash
# Drive the Push 2 display with the animated demo (no FL Studio needed).
#
#   ./run-demo.sh                 # loop forever (Ctrl-C to stop)
#   ./run-demo.sh --demo-frames 120   # run a fixed number of frames
#   any extra args are passed straight through to the daemon.
#
# Quit Ableton Live first — it claims the Push 2 display over USB.

set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "No venv found. Create it first:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

exec "$PY" -m display_daemon --demo "$@"
