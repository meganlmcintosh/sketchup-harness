---
name: sketchup-interior
description: Show the inside of each floor in 3D, furnished and with the roof lifted off, redrawn from the latest plan and opened in SketchUp.
argument-hint: "[house]"
disable-model-invocation: true
allowed-tools:
  - Bash(./bin/plan *)
  - Bash(./bin/sketchup *)
  - Bash(./bin/supex status)
---

# Inside, in 3D

Read `.claude/skills/sketchup-all/steps.md` and follow it, for the house
they named, if any: $ARGUMENTS

- Redraw: with SketchUp.
- Show: each storey's inside view, `views/NN-<storey>-3d.png` (every view
  ending in `-3d.png` except `01-3d.png`), lowest storey first.
- Wrap up: point them to the "<Storey> - 3D" scene tabs.
