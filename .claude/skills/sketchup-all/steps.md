# Showing the house

The steps behind the `sketchup-*` skills. Each skill says whether it needs
SketchUp and which pictures to show; everything else is here.

The person may be designing a house rather than working on the harness, so
follow CLAUDE.md's section on that: plain words about the house, no commands
or file paths unless they ask, and say what a step does before it asks for
their approval.

## 1. Which house

- If they named one, find it: a folder under `projects/`, the path of a
  folder holding a `plan.yaml`, or a word from a folder's name ("smith").
- Otherwise look for `*/plan.yaml` in `projects/` and in each additional
  working directory of this session (their own plans may be in a private
  repo). Leave out `example-townhouse` unless it's the only one or they ask
  for it.
- One house: use it. Several: ask which, offering the one whose `plan.yaml`
  changed last. None: offer to design one with `/floor-plan`.

## 2. Redraw

Always redraw, so the pictures match the plan as it is now; a house takes
about a minute at most. Run commands from the repo root exactly as written:
those are the forms the skill pre-approves.

**Sheets only:**

```bash
./bin/plan build <house>
```

**With SketchUp:** there is no SketchUp in a cloud session
(`CLAUDE_CODE_REMOTE=true`). There, show the pictures already in
`<house>/out/`, and say when they were made and that later changes to the
plan aren't in them. On the Mac, both commands below can wait a while (for
SketchUp to start, or for another session's run to finish), so run them in
the background or with the longest timeout.

1. `./bin/supex status` should say Connected. If not, say you're opening
   SketchUp and run `./bin/sketchup`. If SketchUp is open without the bridge
   (often still on its Welcome window), ask them to save their work and quit
   SketchUp, then run it again. If another SketchUp holds the port
   (SketchUp 2024, or one open in another Mac login), ask them to quit that
   one.
2. Say in a sentence that this redraws the house and opens it in SketchUp,
   replacing the last import but keeping anything drawn by hand in that
   model. Then run:

   ```bash
   ./bin/plan sketchup <house>
   ```

   If it says SketchUp is busy with another run, another session is using
   SketchUp: tell them it's waiting its turn. It carries on by itself (for
   up to 15 minutes); never quit or restart SketchUp to get past the wait.

If a command stops with:

- `plan.yaml error`: the plan itself is broken. Explain the problem in plain
  words and offer to fix it with `/floor-plan`. Don't pass off older
  pictures as current.
- "exists but isn't the active model": the house is open in a SketchUp
  window that isn't in front, or an empty new window is. Ask them to click
  the house's window (or close the empty one), then run it again. Never save
  over the house's `.skp` from another window.

## 3. Look, then show

Read each picture before showing it. If something looks wrong (walls
missing, furniture through a wall, a floating roof), say so plainly rather
than presenting it as finished. Then put the pictures in front of them (send
or attach the files if you can, otherwise link them), with a line on each.

What the files in `<house>/out/` show:

| File | Shows |
| --- | --- |
| `plan-<storey>.png` and `.pdf` | A storey's floor plan sheet: rooms, sizes, areas and dimensions. The PDF is A3, ready to print or send. |
| `plan-roof.png` and `.pdf` | The roof plan. |
| `views/01-3d.png` | The outside of the whole house, from above one corner. |
| `views/NN-<storey>-3d.png` | Inside that storey, furnished, with the roof and any floor above lifted off. |
| `views/NN-<storey>-plan.png` | SketchUp's own plan of that storey. |

## 4. Wrap up

Pass on any warnings in plain words. If SketchUp was used, the house is open
there and saved as `<house>/out/<folder name>.skp`. The scene tabs along the
top of its window switch views: "3D" is the outside, "<Storey> - 3D" the
inside with the roof off, and "<Storey> - Plan" the plan.

## 5. Save

Redrawing can leave `out/` changed even when nobody touched the plan (a
harness update, a stale render). Follow CLAUDE.md's rule on diagram
projects: if `plan.yaml` lives outside this repo, commit those changes
yourself, straight to its main branch — never a PR. Leave `example-townhouse`
uncommitted; it belongs in whatever harness PR is already in progress.
