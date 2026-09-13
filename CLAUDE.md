# Working in this repo

This is a harness for drawing floor plans and furnished 3D houses. A plan is
written as `projects/<name>/plan.yaml`. The Python package `floorplan/` turns
it into DXF files with ezdxf: 2D drafting per storey, a roof plan, and a 3D
model. It also renders PDF sheets and imports the result into a running
SketchUp through the supex bridge (`vendor/supex/`).

```
plan.yaml ──floorplan (ezdxf)──▶ out/*.dxf, *.pdf, *.png, sketchup.json
                                     │
                     src/floorplan_import.rb via supex
                                     ▼
                   SketchUp: tagged components, scenes, views/*.png
```

For plan work (briefs, surveys, photos or PDFs of plans), follow the
`floor-plan` skill (`.claude/skills/floor-plan/SKILL.md`). The format is in
`docs/plan-spec.md`; `./bin/plan reference` lists what's available.

## When the person is designing a house, not the harness

Some people use this repo from the Claude desktop app only to plan a house,
without knowing the code. When the conversation is about the house rather than
the harness:

- Run the commands yourself. Never ask them to open a terminal or edit YAML,
  and before a step that will ask for their approval, say in plain words what
  it does.
- Talk about rooms, sizes, light and flow, not files and commands. Show the
  result: the plan sheet PNGs, then the SketchUp views.
- Ask design questions a few at a time, each with a sensible default they can
  simply accept.

## Ground rules

**Run the tools through `bin/`, never `vendor/supex/` directly.** The wrappers
set `SUPEX_PROJECT_ROOT` to the repo root and put uv on PATH. Without the root,
the runtime's path policy rejects every file operation outside `vendor/supex/`
with error `-32002`. If you see that error, this is why.

**`vendor/supex/` is read-only.** It is vendored upstream code, pinned to a
commit recorded in `vendor/.supex-commit`. Never edit it. If something there
needs to change, the fix belongs upstream or in a patch documented in
`VENDOR.md`. Raise it rather than editing in place, because the next vendor
refresh silently discards local edits.

**`plan.yaml` is the source of truth; `out/` is disposable.** Never hand-edit
generated DXF, PDF or SKP files; change the plan or the generator and rebuild.
A model must be reproducible by rebuilding.

**Geometry comes from committed code.** Modelling logic lives in `floorplan/`
(Python); what runs inside SketchUp lives in `src/` (Ruby) and is run with
`eval_ruby_file`/`bin/supex eval-file`. Inline `eval_ruby` is for probing and
inspection only.

**Verify visually before reporting done.** Read the PNG sheets after
`bin/plan build`, and the `out/views/*.png` scene images after
`bin/plan sketchup`. Model statistics and passing tests confirm that entities
exist; they do not confirm the thing looks right. Both matter.

**Wrap model mutations in an operation.** Use
`model.start_operation("Name", true)` / `model.commit_operation` so changes are a
single undo step for the user. A half-applied change with no undo is worse than
no change. Know that `model.import` closes whatever operation is open (see
below), so do imports between operations and clean up by hand if the step
after them fails; `src/floorplan_import.rb` shows the pattern.

**Australian and metric by default.** Millimetres in plans (areas in m²),
Australian building conventions and sizes (`floorplan/au_defaults.py`), unless
the user says otherwise.

## Things that are not obvious

- SketchUp's DXF importer: options must be **symbol** keys (string keys are
  silently ignored); the whole file arrives as one component named after it;
  text, dimensions and transparency are dropped; colours become `<auto>N`
  materials; block contents on layer `0` land on a stray tag; a block name
  imported twice gets mangled ("Robe 1800" and "Robe 1800" become "Robe #1").
  It merges coplanar faces **only across edges that match exactly**, so
  generated faces must not have T-junctions.
- How the geometry stays watertight (`floorplan/geometry/solid.py`): every
  solid is built from ONE planar arrangement of all its outlines, snap-rounded
  to 0.1 mm, and every face is a cell of that arrangement or a cell edge
  extruded. Never round inputs separately, never union pieces and re-snap:
  both were tried and leak at any wall angle other than 0/90. Three GEOS
  details the arrangement code works around: `set_precision` does not
  re-node linework (so `shapely.node` follows it); the polygonizer only joins
  lines at their endpoints (so linework is exploded into single segments);
  and a corner computed to lie on another edge sits a rounding error off it,
  which the exact predicates treat as a near miss (so vertices are inserted
  into segments within 0.01 mm first). `tests/test_robustness.py` sweeps
  rotations, stair bearings and N-gon roofs; keep it passing.
- `Sketchup.open_file` / `file_new` take effect only after the Ruby call
  returns, and opening an already-open file doesn't bring its window
  forward. That's why `src/floorplan_target.rb` runs and is polled before
  the import. A blank model is never accepted when the project's .skp already
  exists: saving would overwrite hand-drawn work.
- The bridge starts on a timer that doesn't fire while the Welcome window is
  up. `bin/sketchup` opens a blank template copy to avoid it; the loader from
  `bin/install-bridge` starts the bridge however SketchUp is opened.
- The runtime's path policy (`-32002`) depends on `SUPEX_PROJECT_ROOT` in
  SketchUp's own environment (set by `bin/sketchup` via launchd, or by the
  plugin loader), not on the CLI's environment.
- Each finish needs a unique RGB (the import names materials by colour).
- Each `bin/plan sketchup` run writes its own job file and stub under `.tmp/`
  and checks the report's nonce; the bridge's retry is disabled because a
  re-sent import would run twice.

## SketchUp API notes

- SketchUp 2026 bundles Ruby 3.2.2. Match that; don't use newer syntax.
- Model changes must happen on SketchUp's main thread. The bridge handles this;
  don't spawn threads that touch the model.
- Units are inches internally, regardless of what the model displays. Convert
  explicitly (`Numeric#mm`) and say which unit a script's inputs are in.
- `Geom::Point3d` and friends are mutable and are frequently aliased. Duplicate
  before mutating unless you mean to affect the original.

## Cloud sessions

Claude Code on the web runs a clone of this repo in a Linux container
(`CLAUDE_CODE_REMOTE=true`), with no SketchUp and no rv Ruby. The
SessionStart hook (`.claude/hooks/cloud-setup.sh`) installs uv, Python and
the packages, so `bin/plan check` and `build`, pytest and ruff work there;
`bin/sketchup`, `bin/supex`, `bin/plan sketchup` and the supex MCP server
don't (`bin/mcp` exits straight away).

- Go as far as `bin/plan build` and verify with the PNG sheets.
- Commit and push the branch, and say in the report that the SketchUp import
  and its `out/views/*.png` check still need a session on the Mac.
- `bin/rubocop` expects rv's Ruby. If you changed Ruby, install RuboCop 1.82.1
  (with rubocop-ast 1.48.0) into a gem directory with `gem`, and run
  `bin/rubocop` with `RUBOCOP_GEM_HOME` set to that directory and
  `RUBOCOP_RUBY_HOME` to the system Ruby's prefix; otherwise report the Ruby
  as unlinted.
- Don't try to reach SketchUp from the cloud, for instance by tunnelling to
  the bridge's port: the bridge runs whatever Ruby it is sent.
- A session has only what's been pushed. Plans kept in another repository
  can be added to the same session; pass `bin/plan` the project's path.

## Before you finish

- `./bin/plan check` passes for any plan you touched, with no warnings you
  haven't raised with the user.
- Python: `uv run pytest` and `uv run ruff check floorplan tests` pass (run
  from the repo root with `PYTHONPATH=.`).
- Ruby in `src/` and `plugin/` passes `./bin/rubocop` (house style from
  `vendor/supex/runtime/.rubocop.yml`, targeting Ruby 3.2).
- Imports are re-runnable: running twice replaces rather than doubles.
- If you changed how the harness is set up or used, update `README.md` and
  `docs/plan-spec.md` to match.
