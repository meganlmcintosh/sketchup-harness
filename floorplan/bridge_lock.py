"""The SketchUp lock: one run drives SketchUp at a time, whichever session,
checkout or worktree it comes from.

SketchUp runs bridge calls one at a time, but a `bin/plan sketchup` run is
several calls (make the project's model active, poll until it is, import),
and another session's calls can land in between: switching the active model,
or quitting SketchUp mid-import. So `bin/plan sketchup` (sketchup.py) and
`bin/sketchup` hold an exclusive flock on one file per bridge port while they
drive SketchUp, and anything else that wants it waits, saying what for.

- The file is outside the repo, in ~/Library/Caches/sketchup-harness/.
  Worktrees in .claude/worktrees/ are inside the bridge's root, so they drive
  the same SketchUp, but each has its own .tmp/; and $TMPDIR can differ
  between sessions. SKETCHUP_HARNESS_LOCK overrides the path (the tests use it).
- The kernel releases a flock when the process holding it exits or crashes,
  so nothing expires and there is nothing to clean up. Never delete or replace
  the file: the lock belongs to the file, and a new file at the same path is a
  separate lock that nobody holds.
- The holder writes who it is into the file, so a waiting run can say what it
  is waiting for without asking the bridge, which can't answer while SketchUp
  is busy.
- Only the harness's own commands take it; MCP tool calls and hand-run
  bin/supex don't. And if a holder is killed mid-call, the lock goes at once
  but SketchUp still finishes that call, so the next run can queue behind it.

bin/sketchup is a shell script and macOS has no flock command, so it opens the
file on a descriptor and runs `python -m floorplan.bridge_lock take` on that.
A flock belongs to the open file, not the process: the shell keeps holding
the lock after the helper exits, until the shell itself exits.
"""

import argparse
import contextlib
import fcntl
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIT = 15 * 60  # seconds; outlasts a run that sits out every timeout in sketchup.py
POLL = 0.5  # seconds between tries while waiting
FIELDS = {"what", "pid", "started", "checkout"}


class Busy(RuntimeError):
    pass


def lock_path() -> Path:
    if override := os.environ.get("SKETCHUP_HARNESS_LOCK"):
        return Path(override)
    port = os.environ.get("SUPEX_PORT", "9876")
    return Path.home() / "Library" / "Caches" / "sketchup-harness" / f"bridge-{port}.lock"


def _say(message: str) -> None:
    print(message, flush=True)  # flushed, so it lands after what the command printed before it


@contextlib.contextmanager
def held(what: str, wait: float = WAIT, say: Callable[[str], None] = _say) -> Iterator[None]:
    """Hold the lock for the body of a `with`. `what` tells anyone waiting what is running."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        take(fd, what, wait=wait, say=say)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                os.ftruncate(fd, 0)  # a released lock names nobody
    finally:
        os.close(fd)  # closing the file releases the lock


def take(fd: int, what: str, pid: int | None = None, wait: float = WAIT, say: Callable[[str], None] = _say) -> None:
    """Lock `fd`, which is open on the lock file, waiting up to `wait` seconds; then record the holder."""
    start = time.monotonic()
    shown = None
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            holder = _read(fd)
        waited = time.monotonic() - start
        if waited >= wait:
            state = f"still busy after {_duration(wait)}" if shown is not None else "busy"
            raise Busy(f"SketchUp is {state} with {describe(holder)}. Run this again once that has finished.")
        if shown is None or (holder and holder != shown):
            say(f"SketchUp is busy with {describe(holder)}; waiting up to {_duration(wait - waited)} for it.")
            shown = holder
        time.sleep(POLL)
    if shown is not None:
        say(f"SketchUp is free after {_duration(time.monotonic() - start)}.")
    record = {"what": what, "pid": pid or os.getpid(), "started": time.time(), "checkout": str(ROOT)}
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps(record).encode(), 0)


def describe(holder: dict) -> str:
    """A holder's record as 'bin/plan sketchup smith-house (pid 4321, since 14:02:05)'."""
    if not holder:
        return "another run"
    since = time.strftime("%H:%M:%S", time.localtime(holder["started"]))
    where = "" if holder["checkout"] == str(ROOT) else f", in {holder['checkout']}"
    return f"{holder['what']} (pid {holder['pid']}, since {since}{where})"


def _read(fd: int) -> dict:
    """The holder's record, or {} while there is none or it is half written."""
    try:
        holder = json.loads(os.pread(fd, 4096, 0))
    except ValueError:
        return {}
    return holder if isinstance(holder, dict) and holder.keys() >= FIELDS else {}


def _duration(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds >= 120 else f"{seconds:.0f}s"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m floorplan.bridge_lock", description="The SketchUp lock.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("path", help="print the lock file's path, creating its folder")
    p = sub.add_parser("take", help="lock a descriptor, open on the lock file, that this process inherited")
    p.add_argument("--fd", type=int, required=True)
    p.add_argument("--pid", type=int, required=True, help="the process that holds the descriptor")
    p.add_argument("--what", required=True, help="what is about to drive SketchUp, for anyone waiting")
    p.add_argument("--wait", type=float, default=WAIT, help=f"seconds to wait for the lock (default {WAIT})")
    args = parser.parse_args(argv)

    path = lock_path()
    if args.command == "path":
        path.parent.mkdir(parents=True, exist_ok=True)
        print(path)
        return
    try:
        same = os.path.samestat(os.fstat(args.fd), os.stat(path))
    except OSError:
        same = False
    if not same:
        sys.exit(f"descriptor {args.fd} isn't open on {path}")
    try:
        take(args.fd, args.what, pid=args.pid, wait=args.wait)
    except Busy as busy:
        sys.exit(str(busy))


if __name__ == "__main__":
    main()
