import json

import ezdxf

from floorplan.build import build


def test_build_writes_valid_outputs(example_project):
    result = build(example_project)
    out = example_project / "out"
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "model.dxf", "plan-first-floor.dxf", "plan-first-floor.pdf", "plan-first-floor.png",
        "plan-ground-floor.dxf", "plan-ground-floor.pdf", "plan-ground-floor.png",
        "plan-roof.dxf", "plan-roof.pdf", "plan-roof.png", "sketchup.json",
    ]  # fmt: skip
    for dxf in out.glob("*.dxf"):
        assert not ezdxf.readfile(dxf).audit().has_errors, dxf.name
    assert all(sheet.scale == 100 for sheet in result.sheets)

    model = ezdxf.readfile(out / "model.dxf")
    assert [i.dxf.name for i in model.modelspace().query("INSERT")] == [
        "S1-STRUCTURE", "S1-OPENINGS", "S1-STAIRS", "S1-FURNITURE",
        "S2-STRUCTURE", "S2-OPENINGS", "S2-BALUSTRADE", "S2-FURNITURE",
        "ROOF-S2", "ROOF-S1",
    ]  # fmt: skip
    names = json.loads((out / "sketchup.json").read_text())["model"]["definitions"]
    assert any(label.startswith("Sliding Door 3010 x 2100") for label in names.values())
    assert len(set(names.values())) == len(names), "component names are unique"

    manifest = json.loads((out / "sketchup.json").read_text())
    assert manifest["project_id"] == "example-townhouse"
    ground = manifest["plans"][0]
    assert ground["tag"] == "Ground Floor - Plan" and ground["level"] == 0
    assert any(label["text"].startswith("STUDY") for label in ground["labels"])
    rgbs = [tuple(m["rgb"]) for m in manifest["materials"]]
    assert len(rgbs) == len(set(rgbs)), "material colours must be unique"


def test_rebuild_removes_stale_sheets(example_project):
    build(example_project, sheets=False)
    plan = example_project / "plan.yaml"
    plan.write_text(plan.read_text().replace("First Floor", "Upstairs"))  # the storey and the roof's `over`
    build(example_project, sheets=False)
    names = {p.name for p in (example_project / "out").iterdir()}
    assert "plan-upstairs.dxf" in names and "plan-first-floor.dxf" not in names
