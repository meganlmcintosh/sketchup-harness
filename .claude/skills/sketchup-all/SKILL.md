---
name: sketchup-all
description: Show everything for the house, floor plans, roof plan and 3D views outside and in, redrawn from the latest plan and opened in SketchUp.
argument-hint: "[house]"
disable-model-invocation: true
allowed-tools:
  - Bash(./bin/plan *)
  - Bash(./bin/sketchup *)
  - Bash(./bin/supex status)
---

# Everything

Read `steps.md` beside this file (`.claude/skills/sketchup-all/steps.md`) and
follow it, for the house they named, if any: $ARGUMENTS

- Redraw: with SketchUp (that writes the sheets as well).
- Show, in this order: each storey's floor plan sheet, the roof plan, the
  outside, each storey's inside, then SketchUp's plan views. Mention the PDFs.
- Wrap up: all of it.
