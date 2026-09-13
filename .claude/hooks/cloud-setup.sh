#!/usr/bin/env bash
# SessionStart hook, registered in .claude/settings.json. Claude Code cloud
# sessions start in a fresh Linux container with no SketchUp, so this installs
# what bin/plan, pytest and ruff need there: uv if the image lacks it, then
# Python and the packages. `uv run` would install them on first use anyway;
# doing it here surfaces a failure at the start, and the message at the end
# tells Claude which half of the harness it has.
#
# On the Mac (CLAUDE_CODE_REMOTE unset) it does nothing; README.md's setup
# covers that.
set -euo pipefail
[[ "${CLAUDE_CODE_REMOTE:-}" == "true" ]] || exit 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"

# The default cloud image has uv. PyPI is on the default network allowlist;
# astral.sh, where README.md's installer comes from, is not.
if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --quiet --user --break-system-packages uv >&2 || true
fi

# A SessionStart hook's stdout goes into Claude's context: print the outcome
# and, on failure, the end of uv's output.
if log="$(uv sync --project "$ROOT" 2>&1)"; then
  echo "Cloud session: uv sync done, so bin/plan check/build, pytest and ruff work. There is no SketchUp here; see 'Cloud sessions' in CLAUDE.md."
else
  echo "Cloud session: uv sync failed, so bin/plan and the tests won't run until it's fixed. There is no SketchUp here either; see 'Cloud sessions' in CLAUDE.md. uv said:"
  tail -n 15 <<<"$log"
fi
