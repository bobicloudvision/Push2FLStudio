#!/usr/bin/env bash
# Build a single self-contained 'push2-daemon' binary (no Python needed to run).
# Output: dist/push2-daemon
#
#   ./build-binary.sh
#
# Requires the venv with deps + pyinstaller installed.

set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
PYI=".venv/bin/pyinstaller"

[[ -x "$PY" ]] || { echo "Create the venv first (see README)."; exit 1; }
[[ -x "$PYI" ]] || "$PY" -m pip install -q pyinstaller

# Locate libusb so it can be bundled (pyusb loads it at runtime via ctypes).
LIBUSB="$("$PY" - <<'EOF'
import ctypes.util
print(ctypes.util.find_library("usb-1.0") or "")
EOF
)"
ADD_BINARY=()
if [[ -n "$LIBUSB" && -f "$LIBUSB" ]]; then
  ADD_BINARY=(--add-binary "$LIBUSB:.")
  echo "Bundling libusb: $LIBUSB"
else
  echo "WARNING: libusb not found; the binary may not reach the display."
fi

"$PYI" --onefile --clean --noconfirm --name push2-daemon \
  "${ADD_BINARY[@]}" \
  --hidden-import rtmidi \
  --hidden-import mido.backends.rtmidi \
  --collect-submodules usb \
  push2_daemon.py

echo
echo "Built: dist/push2-daemon"
echo "Run:   ./dist/push2-daemon --demo"
