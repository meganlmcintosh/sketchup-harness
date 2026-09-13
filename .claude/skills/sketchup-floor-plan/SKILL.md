---
name: sketchup-floor-plan
description: Show the house's floor plans, a sheet for each floor with rooms, sizes, areas and dimensions (and a PDF to print), redrawn from the latest plan.
argument-hint: "[house]"
disable-model-invocation: true
allowed-tools:
  - Bash(./bin/plan *)
---

# Floor plans

Read `.claude/skills/sketchup-all/steps.md` and follow it, for the house
they named, if any: $ARGUMENTS

- Redraw: sheets only. SketchUp isn't needed.
- Show: `plan-<storey>.png` for each storey, lowest first, mentioning the PDF
  beside each. Offer the roof plan too.
- Wrap up: if SketchUp already has the house open, its "<Storey> - Plan"
  scene tabs show the same plans.
