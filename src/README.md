# src/

Ruby scripts that build and modify the models in `models/`.

These are the artefact of this project. A model should be reproducible by
running the scripts here — not assembled from ad-hoc snippets typed into a
chat window and then lost.

Conventions:

- One script per coherent feature or operation.
- Wrap mutations in `model.start_operation(...)` / `commit_operation` so each
  script is a single undo step.
- Make scripts re-runnable — running twice should not double the geometry.
- State the units a script's inputs are in. SketchUp works in inches internally
  no matter what the model displays.

Run one from Claude Code with the bridge's `eval_ruby_file` tool, or directly:

```bash
./bin/supex eval-file src/your-script.rb
```
