#!/usr/bin/env bash
# Resume CR30 research on macOS. Prints state, then hands over to Claude Code.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

echo "=== chromiq-cr30-research @ $REPO ==="
echo; echo "--- git ---"; git log --oneline -5; git status --short
echo; echo "--- hardware lease ---"
[ -f .hardware-lock/LEASE ] && cat .hardware-lock/LEASE || echo "  free"
echo; echo "--- device ---"
ls /dev/cu.usbserial-* 2>/dev/null || echo "  no usbserial node -- is the CR30 plugged in?"
ioreg -w0 -r -n CH554_CDC -l 2>/dev/null | grep -q AppleUSBCHCOM \
  && echo "  driver: Apple AppleUSBCHCOM (built in, nothing to install)" \
  || echo "  driver: NOT bound -- investigate before assuming a protocol fault"
echo; echo "--- STATUS.md (head) ---"; sed -n '1,20p' STATUS.md
echo; echo "--- next experiment (SESSION_HANDOFF.md) ---"
sed -n '/^## Exact next experiment/,/^## Required state/p' SESSION_HANDOFF.md

echo; echo "=== launching Claude Code ==="
command -v claude >/dev/null || { echo "claude not on PATH"; exit 1; }
exec claude "Read CLAUDE.md, STATUS.md and SESSION_HANDOFF.md in this repository \
in full before doing anything else, then follow the session start protocol in \
CLAUDE.md. Do not modify the ChromIQ repository."
