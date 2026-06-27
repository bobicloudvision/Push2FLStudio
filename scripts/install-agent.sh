#!/usr/bin/env bash
# Install (or reinstall) the Push 2 display daemon as a macOS login agent.
# After this, the daemon auto-starts at login and restarts if it dies — you
# never launch it manually.
#
#   scripts/install-agent.sh          # install + start
#   scripts/install-agent.sh --remove # stop + uninstall
#
# Logs: /tmp/push2flstudio.daemon.log  and  .err

set -euo pipefail

LABEL="com.push2flstudio.daemon"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
TEMPLATE="$ROOT/scripts/$LABEL.plist.template"

uid="$(id -u)"

if [[ "${1:-}" == "--remove" ]]; then
    launchctl bootout "gui/$uid/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed $LABEL."
    exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "venv not found at $PYTHON — create it first:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s#__PYTHON__#$PYTHON#g" -e "s#__MODULE_DIR__#$ROOT#g" "$TEMPLATE" > "$PLIST"

# Reload if already present.
launchctl bootout "gui/$uid/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo "Installed and started $LABEL."
echo "  status: launchctl list | grep push2flstudio"
echo "  logs:   tail -f /tmp/push2flstudio.daemon.log"
echo "  remove: scripts/install-agent.sh --remove"
