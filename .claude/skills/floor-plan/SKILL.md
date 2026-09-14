---
name: floor-plan
description: Create or change a house floor plan in this repo from a written brief, measured dimensions, or a photo or PDF of a plan (or any mix), then produce DXF, PDF sheets and a furnished SketchUp model. Use when asked to draw, design, trace, redraw, furnish or modify a plan, add a storey, stair or roof, or get a plan into SketchUp.
---

# Floor plans: brief, survey or image to plan.yaml to DXF, PDF and SketchUp

The plan lives in `projects/<name>/plan.yaml`; every output is generated from
it. Read `docs/plan-spec.md` before writing one, and run `./bin/plan reference`
for the live list of wall types, openings, finishes and items. Default to
Australian conventions and metric units unless told otherwise.

## 1. Set up

- New project: `./bin/plan new <kebab-name>` makes `projects/<name>/`. If the
  user keeps their plans somewhere else (a private repo, say), pass a path
  instead, `./bin/plan new <folder>/<kebab-name>`, and use that path in every
  command. Put what you were given (brief text, photos, PDFs, survey notes) in
  the project's `sources/`.
- Changing an existing plan: read its `plan.yaml` first and keep its origin,
  ids and names stable, so the user's references ("Bed 2") stay valid.

## 2. Turn the input into a plan

### From a written brief

1. Pin down what the layout depends on; ask briefly only for what you can't
   sensibly assume: storeys, bedrooms and bathrooms, rough size or budget
   area, lot width and which side faces the street and north, garage.
2. Write a room schedule with sizes before any coordinates. Rules of thumb
   for Australian project homes (not compliance checks):
   - master bed 3.4 x 3.6+ with WIR 1.8 x 2.0 and ensuite 2.4 x 2.6; other beds 3.0 x 3.0 min with 1.8 robes
   - living 4.0 x 4.5+; kitchen with a 900-1200 walkway; dining for 6 needs 3.0 x 3.4
   - bathroom 2.4 x 2.6 (bath + shower + vanity); WC 0.9 x 1.3; laundry 1.8 x 1.6
   - hallways 1000 clear (900 min); stair zone about 1.0 x 4.0 plus a 950+ landing top and bottom
   - double garage 6.0 x 6.0; alfresco 3.5 x 4.0
3. Zone it: living to the north where possible (sun), bedrooms and wet areas
   grouped (plumbing), entry to the street side, garage wall on a boundary.
4. Lay walls on round numbers, and check the room sizes after wall
   thicknesses are subtracted (`bin/plan check` prints areas).

### From measured dimensions

- Surveys measure inside faces: trace external walls with `align: inside`
  and the measured internal corners, or convert to overall sizes and use
  `outside`. State which you used.
- Add the runs up: each side's rooms plus wall thicknesses must equal the
  overall length. Report any mismatch instead of absorbing it silently.
- Keep measured values exact (e.g. 3645, not 3600). Mark assumed values
  (wall types, ceiling heights) in YAML comments and tell the user.

### From a photo or PDF of a plan

1. Read the image or PDF directly. Find the scale from printed dimension
   strings or a known size (a standard 820 door, a 2400 garage door) and
   never from pixels alone. If nothing gives a scale, ask for one measurement.
2. Take the overall dimensions first, then work room by room clockwise from
   the south-west corner. Note which dimensions are printed and which you
   inferred.
3. Openings: position doors and windows from the dimension strings, or
   proportionally along their wall; standard sizes are fine when unlabelled.
4. Build with `--grid` and compare `out/plan-*.png` against the source side by
   side, room by room: wall positions, door swings, window positions,
   stair direction. Fix and rebuild until they match, then build once more
   without `--grid`.
5. Tell the user what was unreadable or guessed.

## 3. Write plan.yaml

- Origin at the building's south-west corner; x east, y north; mm. Walls
  may run at any angle; a house set at an angle to the street is fine.
- Order: external walls, internal walls (ending on the faces they meet),
  rooms (a point inside each, not on a separator), separators for open-plan
  splits, openings (`at` on the wall line, clear of corners), stairs, items
  (`room` + `against` where possible; `against` takes a bearing for an
  angled wall), then `roof` (one entry per storey usually does; L/T/U
  outlines are handled).
- WC doors swing out (`into:` the hall) or use a cavity slider. Stairs need
  a clear landing where they arrive. Keep windows clear of overhead cupboards
  and bed heads.
- Items: check that clearances, door swings and walkways still work.

## 4. Check, build, look

```bash
./bin/plan check projects/<name>      # fix every error; treat warnings as bugs
./bin/plan build projects/<name>
```

Read `projects/<name>/out/plan-<storey>.png` for each storey and the roof
plan. Look at: doors swinging into walls or furniture, labels on top of
things, rooms that are missing (an unnamed enclosed area means walls or
names are off), dimensions that don't add up.

## 5. SketchUp

In a cloud session (`CLAUDE_CODE_REMOTE=true`) there is no SketchUp: skip
this step, and say in the report that the import still has to run on the
Mac.

SketchUp must be running with the bridge (`./bin/supex status` says
Connected; start it with `./bin/sketchup` if not).

```bash
./bin/plan sketchup projects/<name>
```

If it says SketchUp is busy with another run, another session is using
SketchUp: the command waits its turn (up to 15 minutes) and carries on by
itself. Give it a long timeout, and never quit or restart SketchUp to get
past the wait.

Then read every `projects/<name>/out/views/*.png`: the 3D view, each
storey's cutaway, each flat plan. Statistics don't prove it looks right, so
look. If the import says the active model isn't the project's, ask the user
to bring the project's SketchUp window forward, or close untitled windows,
and rerun; it will not save over an existing project .skp from a blank
window. One project per SketchUp model.

## 6. Report

Give the user the sheet PDFs and PNGs (and the .skp path), the room
schedule with areas, every assumption and guess, and any warnings left.
Plans are concept designs: say so when it matters, and don't present rules
of thumb as NCC compliance.

## 7. Save

Follow CLAUDE.md's rule on diagram projects: if `plan.yaml` lives outside
this repo, commit the changed `plan.yaml` and `out/` there yourself,
straight to its main branch, judging (or asking, with a decision card, if
it's a close call) whether this is an update to the existing project or a
new sibling version. Never open a PR for those commits. If the plan lives
in this repo's own `projects/` instead, leave it uncommitted for the user's
own harness PR.
