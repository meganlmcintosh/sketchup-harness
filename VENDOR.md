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

### Updating

Run on a machine with network access:

```bash
./scripts/update-vendor.sh          # latest main
./scripts/update-vendor.sh <ref>    # a specific tag or commit
```

Review the diff before committing — upstream is an early-stage project and its
protocol and CLI surface are not yet stable. Check `README.md`'s setup steps
still match after any update.
