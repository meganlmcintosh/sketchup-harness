"""The SketchUp lock (floorplan/bridge_lock.py), held by real processes."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from floorplan import bridge_lock, sketchup

ROOT = Path(__file__).resolve().parents[1]

# Another run: holds the lock until its stdin closes.
HOLDER = """
import sys
from floorplan import bridge_lock
with bridge_lock.held(sys.argv[1], say=lambda message: None):
    print("held", flush=True)
    sys.stdin.read()
"""

# What bin/sketchup does: open the lock file on a descriptor, have the helper lock it, carry on.
SHELL = """
LOCK="$("$PYTHON" -m floorplan.bridge_lock path)"
exec 9<>"$LOCK"
"$PYTHON" -m floorplan.bridge_lock take --fd 9 --pid $$ --what "bin/sketchup --quit" || exit 1
echo held
read -r _
"""


@pytest.fixture(autouse=True)
def lock(tmp_path: Path, monkeypatch) -> Path:
    """A lock file of the test's own, never the real one a live run may be holding."""
    path = tmp_path / "bridge.lock"
    monkeypatch.setenv("SKETCHUP_HARNESS_LOCK", str(path))
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    monkeypatch.setenv("PYTHON", sys.executable)
    monkeypatch.setattr(bridge_lock, "POLL", 0.05)
    return path


@pytest.fixture
def spawn():
    """Start a process that prints "held" once it has the lock."""
    procs = []

    def start(args: list[str]) -> subprocess.Popen:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        procs.append(proc)
        assert proc.stdout.readline() == "held\n"
        return proc

    yield start
    for proc in procs:
        proc.kill()
        proc.wait()
        proc.stdout.close()
        if not proc.stdin.closed:
            proc.stdin.close()


def is_free() -> bool:
    try:
        with bridge_lock.held("probe", wait=0, say=lambda message: None):
            return True
    except bridge_lock.Busy:
        return False


def test_a_second_run_is_told_who_has_sketchup(spawn):
    other = spawn([sys.executable, "-c", HOLDER, "bin/plan sketchup other-house"])
    messages = []
    who = rf"bin/plan sketchup other-house \(pid {other.pid}, since \d\d:\d\d:\d\d\)"
    with (
        pytest.raises(bridge_lock.Busy, match=rf"^SketchUp is still busy after 0s with {who}\. Run this again"),
        bridge_lock.held("bin/plan sketchup smith-house", wait=0.2, say=messages.append),
    ):
        pytest.fail("got the lock while another process held it")
    assert len(messages) == 1
    assert messages[0].startswith(f"SketchUp is busy with bin/plan sketchup other-house (pid {other.pid}, since ")


def test_without_a_wait_it_fails_straight_away(spawn):
    spawn([sys.executable, "-c", HOLDER, "bin/plan sketchup other-house"])
    messages = []
    with (
        pytest.raises(bridge_lock.Busy, match=r"^SketchUp is busy with bin/plan sketchup other-house \(pid"),
        bridge_lock.held("bin/plan sketchup smith-house", wait=0, say=messages.append),
    ):
        pass
    assert messages == []


def test_a_waiting_run_goes_ahead_when_the_holder_finishes(lock, spawn):
    other = spawn([sys.executable, "-c", HOLDER, "bin/sketchup --restart"])
    threading.Timer(0.3, other.stdin.close).start()
    messages = []
    with bridge_lock.held("bin/plan sketchup smith-house", wait=10, say=messages.append):
        record = json.loads(lock.read_text())
        assert not is_free()
    assert record["what"] == "bin/plan sketchup smith-house"
    assert record["pid"] == os.getpid()
    assert messages[0].startswith("SketchUp is busy with bin/sketchup --restart (pid ")
    assert messages[-1].startswith("SketchUp is free after ")
    assert lock.read_text() == ""  # a released lock names nobody
    assert is_free()


def test_a_killed_holder_leaves_nothing_to_clean_up(spawn):
    other = spawn([sys.executable, "-c", HOLDER, "bin/plan sketchup other-house"])
    assert not is_free()
    other.kill()
    other.wait()
    assert is_free()


def test_a_shell_keeps_the_lock_after_the_helper_exits(spawn):
    shell = spawn(["bash", "-c", SHELL])  # "held" is printed after the helper has exited
    with (
        pytest.raises(bridge_lock.Busy, match=rf"with bin/sketchup --quit \(pid {shell.pid}, since "),
        bridge_lock.held("bin/plan sketchup smith-house", wait=0, say=lambda message: None),
    ):
        pass
    shell.stdin.close()
    shell.wait()
    assert is_free()


def test_the_helper_refuses_a_descriptor_open_on_another_file(tmp_path):
    with open(tmp_path / "not-the-lock", "w") as other:
        run = subprocess.run(
            [sys.executable, "-m", "floorplan.bridge_lock", "take", "--fd", str(other.fileno()), "--pid", "1",
             "--what", "bin/sketchup"],
            pass_fds=[other.fileno()], capture_output=True, text=True, check=False,
        )  # fmt: skip
    assert run.returncode == 1
    assert "isn't open on" in run.stderr
    assert is_free()


def test_push_holds_the_lock_from_the_first_bridge_call_to_the_last(tmp_path, monkeypatch):
    calls = []

    def bridge(stub_path, job_path, script, module, job, timeout):
        calls.append((module, job.get("mode"), is_free()))
        return {"nonce": job["nonce"], "ready": len(calls) > 1}  # not ready at first, so push polls

    monkeypatch.setattr(sketchup, "_run", bridge)
    monkeypatch.setattr(sketchup, "TMP", tmp_path)
    result = SimpleNamespace(manifest=tmp_path / "sketchup.json", out=tmp_path, project_id="smith-house")
    sketchup.push(result)
    assert calls == [
        ("FloorplanTarget", "prepare", False),
        ("FloorplanTarget", "status", False),
        ("FloorplanImport", None, False),
    ]
    assert is_free()
