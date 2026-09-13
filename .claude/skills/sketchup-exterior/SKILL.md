---
name: sketchup-exterior
description: Show the outside of the house in 3D, redrawn from the latest plan and opened in SketchUp.
argument-hint: "[house]"
disable-model-invocation: true
allowed-tools:
  - Bash(./bin/plan *)
  - Bash(./bin/sketchup *)
  - Bash(./bin/supex status)
---

# Outside, in 3D

Read `.claude/skills/sketchup-all/steps.md` and follow it, for the house
they named, if any: $ARGUMENTS

- Redraw: with SketchUp.
- Show: `views/01-3d.png`.
- Wrap up: point them to the "3D" scene tab to orbit around the outside.
