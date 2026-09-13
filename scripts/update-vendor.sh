#!/usr/bin/env bash
# Refresh vendor/supex from upstream. Requires network access.
#
#   ./scripts/update-vendor.sh          # latest main
#   ./scripts/update-vendor.sh v0.3.0   # a specific tag or commit
set -euo pipefail

REPO="https://github.com/darwin/supex.git"
REF="${1:-main}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor/supex"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Fetching $REPO @ $REF ..."
git clone --quiet "$REPO" "$TMP/supex"
git -C "$TMP/supex" checkout --quiet "$REF"

SHA="$(git -C "$TMP/supex" rev-parse HEAD)"
OLD="$(cat "$ROOT/vendor/.supex-commit" 2>/dev/null || echo none)"

if [ "$SHA" = "$OLD" ]; then
  echo "Already at $SHA — nothing to do."
  exit 0
fi

rm -rf "$DEST"
mkdir -p "$DEST"
tar --exclude=.git -C "$TMP/supex" -cf - . | tar -C "$DEST" -xf -
printf '%s\n' "$SHA" > "$ROOT/vendor/.supex-commit"

echo
echo "Updated: $OLD -> $SHA"
echo
echo "Next:"
echo "  1. Update the pinned commit and date in VENDOR.md and NOTICE."
echo "  2. Review the diff — upstream's protocol and CLI are not yet stable."
echo "  3. Re-lock the driver's environment: uv lock --project supex-env"
echo "     (if uv can't resolve mcp, see 'Python dependencies' in VENDOR.md)."
echo "  4. Re-check the setup steps in README.md still match, and re-run ./bin/install-bridge if you use it."
echo "  5. Reconnect and run: ./bin/supex status"
echo "  6. Re-run ./bin/plan sketchup projects/example-townhouse and check out/views/*.png."
