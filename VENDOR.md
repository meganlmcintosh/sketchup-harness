# Vendored dependencies

## vendor/supex

- **Upstream**: https://github.com/darwin/supex
- **Licence**: MIT (see `vendor/supex/LICENSE`)
- **Pinned commit**: `bf503c910551a34ec7439da2d02927b04e7e987b` (tagged v0.2.0, 2025-12-14)
- **Branch**: `main` — upstream's stable line. Active development happens on
  upstream's `dev` branch.
- **Local modifications**: none. The tree is unmodified upstream.

### Why vendored rather than a submodule

The Mac this repo is developed on reaches the network only from macOS itself,
not from every tool that touches the tree. Vendoring keeps the harness working
with no network and no submodule init, and pins us to a known-good commit
rather than whatever upstream's HEAD happens to be.

### Not vendored

Upstream declares one submodule, `docgen/sketchup-api-stubs`
(https://github.com/SketchUp/ruby-api-stubs), which is **not** included here.
It is only needed to regenerate upstream's API documentation. If you want it:

```bash
git clone https://github.com/SketchUp/ruby-api-stubs.git vendor/supex/docgen/sketchup-api-stubs
```

### Python dependencies: `supex-env/`

Upstream ships no lockfile, and the v0.2.0 driver asks for `mcp[cli]>=1.3.0`
with no upper bound. mcp 2.0.0 (July 2026) renamed `FastMCP` to `MCPServer`
and left `mcp/server/fastmcp.py` as a stub that raises on import. An unpinned
install therefore gets mcp 2, and the MCP server dies at startup with
`ImportError: cannot import name 'fastmcp' from 'mcp.server'`. The stub's own
error names the fix, but Python discards it because `server.py` imports the
module as `from mcp.server import fastmcp`. The CLI never imports mcp, so
`bin/supex` kept working.

The harness runs the driver from `supex-env/` instead, a uv project outside
the vendored tree. It installs `vendor/supex/driver` as an editable path
dependency, constrains `mcp<2` (`constraint-dependencies`), and commits its
`uv.lock`. `bin/mcp` and `bin/supex` export `UV_PROJECT=supex-env`, which
redirects the plain `uv run` inside upstream's `mcp` and `supex` wrappers.
`update-vendor.sh` only replaces `vendor/supex/`, so all of this survives a
refresh.

Upstream v0.3.0 (2026-09-07) already moved the driver to mcp 2
(`mcp[cli]>=2.1.1,<3`). Its wrappers also call
`uv run --project <driver>`, which overrides `UV_PROJECT`. Updating to v0.3.0
or later means dropping the constraint and reworking `bin/mcp` and
`bin/supex`, not just re-locking.

### Updating

Run on a machine with network access:

```bash
./scripts/update-vendor.sh          # latest main
./scripts/update-vendor.sh <ref>    # a specific tag or commit
```

Review the diff before committing — upstream is an early-stage project and its
protocol and CLI surface are not yet stable. Check `README.md`'s setup steps
still match after any update. Re-lock with `uv lock --project supex-env` and
commit the lockfile with the update. If uv can't resolve `mcp`, the new driver
has outgrown the constraint (see above).

### What the harness relies on

Check these still hold after an update; each one breaks something quietly if
it changes:

- `runtime/src/injector.rb` loads the runtime (used by `bin/sketchup` and the
  `plugin/` loader), and the runtime autostarts its bridge on a `UI.start_timer`.
- `supex eval-file --raw` prints one JSON object with `success` and `result`
  (parsed by `floorplan/sketchup.py`), and the CLI honours `SUPEX_TIMEOUT`.
- The path policy allows `SUPEX_PROJECT_ROOT` (`runtime/src/supex_runtime/path_policy.rb`).
- `runtime/.rubocop.yml` is the house style `.rubocop.yml` inherits.
- The `mcp` and `supex` wrappers start the driver with a plain `uv run` from
  `driver/`, with no `--project`, so `UV_PROJECT` moves them into `supex-env/`.
  If that changes, they silently go back to an unpinned environment of their own.

Running the vendored tools writes, but does not edit, files inside the tree:
`.tmp/` (the MCP server's log and SketchUp's console capture) and Python's
`__pycache__/` directories. Both are git-ignored, and `update-vendor.sh`
deletes them. uv puts the driver's environment in `supex-env/.venv/`, outside
the tree. Checkouts set up before `supex-env/` existed also have
`driver/.venv/` and `driver/uv.lock`, holding mcp 2. Nothing uses them now, and
they can be deleted.
