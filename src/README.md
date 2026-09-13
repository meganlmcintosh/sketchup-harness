# src/

Ruby that runs inside SketchUp through the supex bridge. The modelling logic
itself is the Python generator in `floorplan/`; these scripts bring its output
into SketchUp.

| Script | What it does |
| ------ | ------------ |
| `floorplan_target.rb` | Makes the project's model the active one (opens it, or starts a new model), polled by `bin/plan sketchup` because opening a file only takes effect after the call returns. |
| `floorplan_import.rb` | Imports a build (`model.dxf` and one plan DXF per storey), replaces any previous import of the project, repairs tags and materials, adds labels and dimensions, builds scenes, saves the model and writes a PNG of each scene. |

Both read `.tmp/floorplan-job.json`, which `bin/plan sketchup` writes, so there
is no inline Ruby with arguments baked in.

Conventions for anything added here:

- Wrap model changes in `model.start_operation(...)` / `commit_operation`, so
  each run is a single undo step.
- Make scripts re-runnable: running twice must not double the geometry.
- State the units a script's inputs are in. SketchUp works in inches internally
  no matter what the model displays; convert with `Numeric#mm`.
- Pass `./bin/rubocop`.

Run one directly with:

```bash
./bin/supex eval-file src/your-script.rb
```
