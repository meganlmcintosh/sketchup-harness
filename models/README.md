# models/

`.skp` files under version control.

SketchUp files are binary, so git stores each revision whole and cannot show a
meaningful diff. Two consequences worth knowing:

- The repo grows quickly if large models are committed often. Commit meaningful
  states, not every save.
- The scripts in `src/` are the readable history of how a model was built. The
  `.skp` is the output. When they disagree, trust the scripts.

SketchUp's own backup and autosave files (`.skb`, `AutoSave_*.skp`) are ignored
by `.gitignore`.
