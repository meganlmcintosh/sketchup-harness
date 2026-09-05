# sketchup-harness

A Claude Code harness for working on SketchUp files — describe a change in natural
language, and have Claude write and execute SketchUp Ruby against the live model.

## How it works

SketchUp's `.skp` format is proprietary and there is no practical way to author one
from outside the application. So the harness drives a *running* SketchUp instead:

```
┌──────────────┐      ┌──────────────────┐      ┌────────────────────┐
│ Claude Code  │─────▶│  Python driver   │─────▶│ SketchUp + Ruby    │
│  (macOS)     │  MCP │  (MCP server)    │ TCP  │ bridge extension   │
└──────────────┘      └──────────────────┘      └────────────────────┘
                             JSON-RPC 2.0 over localhost:9876
```

A Ruby extension loaded inside SketchUp listens on a localhost socket. A Python MCP
server outside it exposes tools to Claude Code. Claude sends Ruby, the extension
evaluates it against the active model, and geometry appears in the open document.

The part that makes this usable rather than blind is the return path: the bridge
sends back model statistics, entity listings and **screenshots**, so Claude can see
what it built and correct itself without you relaying every result by hand.

## Layout

| Path            | What it is                                                       |
| --------------- | ---------------------------------------------------------------- |
| `vendor/supex/` | Upstream [supex](https://github.com/darwin/supex), unmodified. The bridge itself. |
| `bin/`          | Repo-scoped wrappers around the vendored tools. Use these, not `vendor/supex/` directly. |
| `src/`          | Our own Ruby scripts — the modelling logic specific to this project. |
| `models/`       | `.skp` files under version control.                              |
| `scripts/`      | Project automation, including vendor refresh.                    |
| `CLAUDE.md`     | Conventions Claude Code follows when working in this repo.       |

We vendor supex rather than fork it: upstream is a general-purpose bridge and
improves independently, while this repo holds the design work. See `VENDOR.md`
for the pinned commit and how to update it.

## Requirements

Everything below runs on the Mac, natively — not in a container.

- **macOS** — the only platform upstream tests
- **SketchUp 2026** — the only version upstream tests; it bundles Ruby 3.2.2
- **Claude Code** — installed and running on that Mac
- **Python 3.14+** — for the MCP driver, managed via `uv`
- **Ruby 3.2.2** — matching SketchUp's bundled interpreter

## Setup

Everything runs on the Mac. From this repo's root:

```bash
# 1. Toolchain (once). Upstream pins Python 3.14 and Ruby 3.2.2 via mise.
brew install mise jq
mise install

# 2. Launch SketchUp with the bridge extension deployed into it.
./bin/sketchup models/your-model.skp

# 3. In a second terminal, register the bridge with Claude Code.
claude mcp add supex -- "$(pwd)/bin/mcp"

# 4. Confirm the connection.
./bin/supex status
```

Step 4 should report the socket state and the SketchUp version it is talking to.
If it can't connect, SketchUp isn't running with the extension loaded — rerun
step 2 and check SketchUp's own Ruby Console for load errors.

### Always use `bin/`, not `vendor/supex/` directly

The three scripts in `bin/` are thin wrappers that set `SUPEX_PROJECT_ROOT` to
this repo before delegating to the vendored tools. Without it the runtime's path
policy refuses to touch anything outside `vendor/supex/`, and every
`eval_ruby_file src/...` or `open_model models/...` fails with error `-32002,
path access denied`. Calling the vendored scripts directly is the most likely
cause of that error.

`bin/sketchup` registers the value with `launchctl` rather than exporting it,
because SketchUp is started through `open`, which does not inherit the shell
environment. If path errors persist, check what SketchUp actually received:

```bash
launchctl getenv SUPEX_PROJECT_ROOT
```

## Working with it

Once connected, you talk to Claude Code normally. It has tools to evaluate Ruby
inline or from a file in `src/`, inspect the model, and screenshot the viewport.

Two habits make the difference:

**Keep the geometry in scripts, not in chat.** Ask for changes as edits to files
in `src/` rather than one-off evaluated snippets. The scripts are the artefact —
they're reviewable, re-runnable, and diffable. A model rebuilt from a script is
reproducible; a model built from forty ad-hoc snippets is not.

**Let it look before it commits.** Screenshots are cheap and Claude corrects far
better from a picture than from a description. Say "check it" and it will.

Direct modelling in SketchUp's GUI is still the better tool for sketching and
quick adjustment. The harness earns its keep on the repetitive, the parametric,
and the fiddly-but-precise.

## Licence

MIT — see `LICENSE`. Vendored upstream code is MIT and separately attributed in
`NOTICE`.
