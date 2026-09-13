"""Push a build into the running SketchUp through the supex bridge.

Each run gets its own job file and a one-line stub in .tmp/ that loads the
committed script in src/ and calls it with that job, so geometry changes
always come from a file in the repo, two runs can't read each other's job,
and a report is only trusted if it echoes the run's nonce:

1. src/floorplan_target.rb makes the project's model active. Opening or
   creating a model only takes effect after the Ruby call returns, so this is
   polled until SketchUp has switched.
2. src/floorplan_import.rb imports, repairs, annotates, saves and renders.

The run holds the SketchUp lock (bridge_lock.py) from its first call to its
last, so a run from another session waits its turn instead of switching the
active model in between.
"""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

from . import bridge_lock
from .build import BuildResult

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / ".tmp"
TARGET = ROOT / "src" / "floorplan_target.rb"
IMPORTER = ROOT / "src" / "floorplan_import.rb"
IMPORT_TIMEOUT = 600  # seconds; a furnished house can take a while to import
QUICK_TIMEOUT = 15  # seconds; the target script only looks at the active model
SWITCH_TIMEOUT = 30  # seconds for SketchUp to open or create the model


class SketchUpError(RuntimeError):
    pass


def push(result: BuildResult, save: bool = True, views: bool = True) -> dict:
    with bridge_lock.held(f"bin/plan sketchup {result.project_id}"):
        return _push(result, save, views)


def _push(result: BuildResult, save: bool, views: bool) -> dict:
    nonce = secrets.token_hex(4)
    job = {
        "nonce": nonce,
        "manifest": str(result.manifest.resolve()),
        "skp": str((result.out / f"{result.project_id}.skp").resolve()),
        "views_dir": str((result.out / "views").resolve()),
        "save": save,
        "views": views,
    }
    TMP.mkdir(exist_ok=True)
    job_path = TMP / f"floorplan-job-{nonce}.json"
    stub_path = TMP / f"floorplan-run-{nonce}.rb"
    try:
        state = _run(stub_path, job_path, TARGET, "FloorplanTarget", {**job, "mode": "prepare"}, QUICK_TIMEOUT)
        deadline = time.time() + SWITCH_TIMEOUT
        while not state.get("ready"):
            if time.time() > deadline:
                if state.get("exists"):
                    raise SketchUpError(
                        f"{Path(job['skp']).name} exists but isn't the active model (active: "
                        f"'{state.get('active') or 'untitled'}'). If it is open in another window, bring that "
                        "window to the front; otherwise close unsaved new windows. Then run again."
                    )
                raise SketchUpError(
                    f"SketchUp did not switch to a new model (active: '{state.get('active') or 'untitled'}'). "
                    "Close unsaved new windows and run again."
                )
            time.sleep(0.5)
            state = _run(stub_path, job_path, TARGET, "FloorplanTarget", {**job, "mode": "status"}, QUICK_TIMEOUT)
        report = _run(stub_path, job_path, IMPORTER, "FloorplanImport", job, IMPORT_TIMEOUT)
    except Exception:
        # Leave the job and stub behind for a look; a good run cleans up below.
        raise
    for path in (job_path, stub_path):
        path.unlink(missing_ok=True)
    return report


def _ruby_string(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _run(stub_path: Path, job_path: Path, script: Path, module: str, job: dict, timeout: int) -> dict:
    job_path.write_text(json.dumps(job, indent=2))
    stub_path.write_text(
        "# Written by bin/plan for one run; safe to delete.\n"
        f"load {_ruby_string(str(script))}\n"
        f"{module}.run({_ruby_string(str(job_path))})\n"
    )
    # The bridge re-sends a call that times out; an import must never run twice.
    env = {**os.environ, "SUPEX_TIMEOUT": str(timeout), "SUPEX_RETRIES": "0"}
    try:
        proc = subprocess.run(
            [str(ROOT / "bin" / "supex"), "eval-file", "--raw", str(stub_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout + 30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SketchUpError(
            f"SketchUp did not answer within {timeout}s while running {script.name}. Is a dialog open in "
            "SketchUp? Dismiss it and run again."
        ) from None
    payload = _last_json(proc.stdout)
    if payload is None or not payload.get("success"):
        detail = payload.get("error") if payload else (proc.stdout + proc.stderr).strip()
        hint = "" if "Connected" in _status() else " Is SketchUp running? Start it with ./bin/sketchup."
        raise SketchUpError(f"{script.name} failed: {detail}{hint}")
    result = payload.get("result")
    try:
        report = json.loads(result) if isinstance(result, str) else result
    except json.JSONDecodeError:
        raise SketchUpError(f"{script.name} returned something other than its report: {result!r}") from None
    if not isinstance(report, dict) or report.get("nonce") != job["nonce"]:
        raise SketchUpError(f"{script.name} answered for a different run: {report!r}")
    return report


def _last_json(text: str) -> dict | None:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _status() -> str:
    try:
        proc = subprocess.run(
            [str(ROOT / "bin" / "supex"), "status"],
            capture_output=True,
            text=True,
            env={**os.environ, "SUPEX_TIMEOUT": "5", "SUPEX_RETRIES": "0"},
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return proc.stdout
