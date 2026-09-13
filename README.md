# sketchup-harness

A Claude Code harness for floor plans. Give Claude a written brief, measured
dimensions, or a photo or PDF of a plan (or a mix). It writes the plan as a
small YAML file, generates 2D and 3D DXF files with
[ezdxf](https://ezdxf.readthedocs.io), renders dimensioned PDF sheets, and
builds a furnished, multi-storey model in a running SketchUp to check.

Australian conventions and metric units by default.

## How it works

```
 brief / survey / photo / PDF
            │  Claude (the floor-plan skill)
            ▼
 projects/<name>/plan.yaml          walls, openings, rooms, stairs, furniture, roof
            │  ./bin/plan build     (Python: floorplan/, ezdxf, shapely, matplotlib)
            ▼
 out/model.dxf                      3D: storeys, doors and windows, stairs, furniture, roof
 out/plan-<storey>.dxf|pdf|png      2D drafting at 1:100 on A3, plus a roof plan
 out/sketchup.json                  what DXF can't carry: names, labels, dimensions, glass
            │  ./bin/plan sketchup  (src/floorplan_import.rb via the supex bridge)
            ▼
 SketchUp: tagged components, flat plans with labels and dimensions,
           scenes per storey, out/<name>.skp and out/views/*.png
```

SketchUp's `.skp` format can't practically be written from outside the app,
but SketchUp Pro (including education licences) imports DXF. The harness
generates DXF, then drives a *running* SketchUp to import it and repair what
the importer loses. A Ruby extension inside SketchUp listens on a localhost
socket; Python tools outside send it Ruby to run.
[supex](https://github.com/darwin/supex) provides that bridge, and its return
path (model stats, screenshots) lets Claude check its own work.

## Layout

| Path | What it is |
| ---- | ---------- |
| `projects/<name>/` | One folder per plan: `plan.yaml`, `sources/` (briefs, photos), `out/` (generated, not committed) |
| `floorplan/` | The generator (Python): spec, geometry kernel, 2D/3D DXF, sheets, stairs, roofs, furniture catalogue |
| `src/` | Ruby run inside SketchUp through the bridge: the import and its target check |
| `plugin/` | The SketchUp loader installed by `bin/install-bridge` |
| `docs/plan-spec.md` | The `plan.yaml` reference |
| `.claude/skills/floor-plan/` | How Claude turns briefs, surveys and images into plans |
| `tests/` | pytest suite, including watertightness checks on all generated solids |
| `bin/` | Entry points: `plan`, `sketchup`, `supex`, `mcp`, `install-bridge`, `rubocop` |
| `vendor/supex/` | Upstream supex, unmodified (see `VENDOR.md`) |
| `models/` | Hand-made `.skp` files under version control |

## Requirements

- **macOS** and **SketchUp 2026** with CAD import (Pro, Studio or an education
  licence). The bridge is only tested on 2026, which bundles Ruby 3.2.2.
- **Claude Code**.
- **uv**, which installs Python 3.14 and all Python packages.
- Optional, for linting the Ruby: **rv** with Ruby 3.4 and RuboCop (below).

Nothing needs Homebrew or Xcode's command line tools, though git does.

## Setup

From this repo's root:

```bash
# 1. uv (user-level, leaves your shell config alone), then Python and packages.
curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
~/.local/bin/uv sync
~/.local/bin/uv sync --project vendor/supex/driver

# 2. Optional: start the bridge however SketchUp is opened (Dock, Finder...).
./bin/install-bridge

# 3. Start SketchUp 2026 with the bridge, straight into a blank model.
./bin/sketchup

# 4. Check the connection.
./bin/supex status
```

`bin/sketchup` launches `/Applications/SketchUp 2026` explicitly
(`SKETCHUP_APP` overrides it) because `open -a SketchUp` picks an arbitrary copy
when several are installed. It opens a copy of the blank template because the
bridge can't start while the Welcome window is showing. `./bin/sketchup --quit`
quits through the bridge and `--restart` relaunches; both discard changes to
that blank copy only and refuse if the active model has unsaved changes, so a
"Save changes?" dialog never blocks SketchUp with nobody to answer it.

**About `bin/install-bridge`.** It copies `plugin/sketchup_harness_bridge.rb`
into SketchUp's Plugins folder, with a sidecar file holding this repo's path,
so the bridge starts with every SketchUp session. The trade-off: while
SketchUp is open, any program on this Mac can send it Ruby through the
localhost port (the REPL server supex would also open is switched off).
Remove it with `./bin/install-bridge --uninstall`; rerun it if you move the
repo.

**MCP tools for Claude Code.** `.mcp.json` registers the supex MCP server
(`bin/mcp`) for this project; Claude Code asks to approve it on the next
session. The `bin/plan sketchup` workflow uses the CLI and works without it.

### Path errors (`-32002`)

Inside SketchUp, the runtime refuses file operations (`eval_ruby_file`,
`open_model`, `save_model`, `take_screenshot`) outside `SUPEX_PROJECT_ROOT`.
That variable has to be in **SketchUp's** environment: `bin/sketchup`
registers it with launchd before launching, and the plugin loader sets it
from its sidecar file. The CLI's own environment makes no difference, so
`vendor/supex/supex` and `bin/supex` behave the same. If you see
`-32002, path access denied`, SketchUp was started some other way; quit it
and use `./bin/sketchup`, or check what it was given:

```bash
launchctl getenv SUPEX_PROJECT_ROOT
```

## Using it

Talk to Claude Code: "draw a single-storey three-bedroom house for a 15 m lot,
living to the north", "trace this plan" (with a photo), "the kitchen is
4.2 by 3.6", "add a double garage with a skillion roof", "furnish it". Claude
writes `plan.yaml` and runs the commands. You can run them yourself too:

```bash
./bin/plan new smith-house                  # start a project
./bin/plan check projects/smith-house       # validate; rooms and areas
./bin/plan build projects/smith-house       # DXFs, PDF and PNG sheets
./bin/plan sketchup projects/smith-house    # build and import into SketchUp
./bin/plan reference                        # wall types, openings, finishes, furniture
```

Try the example: `./bin/plan sketchup projects/example-townhouse`, a furnished
two-storey townhouse with a stair and a hip roof.

Re-running `bin/plan sketchup` replaces that project's previous import and
saves the model to `projects/<name>/out/<name>.skp`. Anything you draw by
hand in that model stays: the import only touches its own components, tags
and scenes, and it refuses to save over an existing `.skp` from a blank
window. Scenes cover the whole house, each storey with the floors above
removed, and each storey's flat plan. An import is three undo steps (the
removal, the DXF imports, the repairs) because SketchUp's importer closes
Ruby operations; if a run fails part way, its own entities are erased again.

Walls can run at any angle; roofs cover L-, T- and U-shaped plans at any
rotation. Plans are concept designs: sizes and stair checks follow common
Australian practice, not a certifier's review.

## Development

```bash
PYTHONPATH=. uv run pytest              # tests, including watertightness sweeps at odd angles
uv run ruff check floorplan tests       # Python lint
./bin/rubocop                           # Ruby lint (src/, plugin/)
```

The geometry kernel builds every solid from one snap-rounded planar
arrangement, so faces share their edges exactly; `CLAUDE.md` records the GEOS
behaviours that approach has to work around. When touching it, keep
`tests/test_robustness.py` passing.

### Ruby lint

macOS's Ruby 2.6 is too old for RuboCop, and building a newer Ruby needs a
compiler. rv installs a prebuilt Ruby instead. RuboCop is pinned to 1.82.1 with
rubocop-ast 1.48.0 because newer releases need a Prism version that must be
compiled:

```bash
curl -LsSf https://rv.dev/install -o /tmp/rv-install.sh && RV_NO_MODIFY_PATH=1 sh /tmp/rv-install.sh
rv ruby install 3.4.10
RUBY_HOME=~/.local/share/rv/rubies/ruby-3.4.10
export GEM_HOME=~/.local/share/rv/tools/rubocop GEM_PATH=~/.local/share/rv/tools/rubocop:$($RUBY_HOME/bin/ruby -e 'print Gem.default_dir')
$RUBY_HOME/bin/gem install rubocop-ast -v 1.48.0 --minimal-deps --no-document --source https://rubygems.org/
$RUBY_HOME/bin/gem install rubocop -v 1.82.1 --minimal-deps --no-document --source https://rubygems.org/
```

The rv installer may put `rv` in `~/.local/bin/bin`; move it to `~/.local/bin`.

## Licence

MIT; see `LICENSE`. Vendored upstream code is MIT and separately attributed in
`NOTICE`.
