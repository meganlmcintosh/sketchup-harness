# Working in this repo

This is a SketchUp automation harness. You drive a running SketchUp instance
through the supex MCP bridge (`vendor/supex/`).

## Ground rules

**Run the tools through `bin/`, never `vendor/supex/` directly.** The wrappers
set `SUPEX_PROJECT_ROOT` to the repo root. Without it the runtime's path policy
rejects every file operation outside `vendor/supex/` with error `-32002`. If you
see that error, this is why.

**`vendor/supex/` is read-only.** It is vendored upstream code, pinned to a
commit recorded in `vendor/.supex-commit`. Never edit it. If something there
needs to change, the fix belongs upstream or in a patch documented in
`VENDOR.md` — raise it rather than editing in place, because the next vendor
refresh silently discards local edits.

**Modelling logic lives in `src/`, as Ruby files.** Prefer `eval_ruby_file` on a
committed script over `eval_ruby` with an inline snippet. Inline evaluation is
for probing and inspection; anything that changes geometry should exist as a file
first. A model must be reproducible by re-running its scripts.

**Verify visually before reporting done.** After geometry changes, screenshot the
viewport and actually look at it. Model statistics confirm that entities exist;
they do not confirm the thing looks right. Both matter.

**Wrap model mutations in an operation.** Use
`model.start_operation("Name", true)` / `model.commit_operation` so changes are a
single undo step for the user. A half-applied change with no undo is worse than
no change.

## SketchUp API notes

- SketchUp 2026 bundles Ruby 3.2.2. Match that; don't use newer syntax.
- Model changes must happen on SketchUp's main thread. The bridge handles this —
  don't spawn threads that touch the model.
- Units are inches internally, regardless of what the model displays. Convert
  explicitly and say which unit a script's inputs are in.
- `Geom::Point3d` and friends are mutable and are frequently aliased. Duplicate
  before mutating unless you mean to affect the original.

## Before you finish

- Ruby in `src/` passes RuboCop (see `vendor/supex/runtime/.rubocop.yml` for the
  house style upstream uses).
- New scripts are re-runnable: running twice should not silently double the
  geometry.
- If you changed how the harness is set up or used, update `README.md` to match.
