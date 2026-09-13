import copy

import pytest
import yaml

from floorplan.spec import SpecError, load_plan, parse_plan
from tests.conftest import EXAMPLE

MINIMAL = {
    "project": {"name": "Test"},
    "storeys": [
        {
            "name": "Ground",
            "walls": [
                {"id": "EXT", "type": "brick_veneer", "closed": True, "align": "outside",
                 "points": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]},
            ],  # fmt: skip
            "rooms": [{"name": "Living", "at": [3000, 2000]}],
            "openings": [{"type": "door", "at": [3000, 0]}, {"type": "window", "wall": "EXT", "offset": 1500}],
        }
    ],
}


def with_changes(change) -> dict:
    data = copy.deepcopy(MINIMAL)
    change(data)
    return data


def test_example_loads():
    plan = load_plan(EXAMPLE)
    assert [s.name for s in plan.storeys] == ["Ground Floor", "First Floor"]
    first = plan.storeys[1]
    assert first.level == 0 + 2700 + 300  # derived from the storey below
    assert first.rooms[0].floor == "carpet"  # "Bed" rooms default to carpet


def test_minimal_defaults():
    plan = parse_plan(MINIMAL)
    storey = plan.storeys[0]
    assert storey.height == 2440 and storey.floor == 300
    door, window = storey.openings
    assert (door.hole_width, door.sill, door.head) == (880, 0, 2100)  # 820 leaf + frame
    assert (window.sill, window.head) == (890, 2100)  # 1210 high under a 2100 head


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["storeys"][0]["walls"][0].update(type="straw_bale"), "unknown wall type"),
        (lambda d: d["storeys"][0]["walls"][0].update(align="left"), "is not one of"),
        (lambda d: d["storeys"][0].update(colour="red"), "unknown key"),
        (lambda d: d["storeys"][0]["openings"].append({"type": "window", "at": [0, 0], "sill": 900, "head": 2100}),
         "not both"),
        (lambda d: d["storeys"][0]["openings"].append({"type": "door", "wall": "NOPE", "offset": 10}),
         "unknown wall id"),
        (lambda d: d["storeys"][0]["openings"].append({"type": "door"}), "either 'at"),
        (lambda d: d["storeys"][0]["rooms"].append({"name": "Living", "at": [1, 1]}), "duplicate room name"),
        (lambda d: d.update(finishes={"mine": {"rgb": [238, 236, 228]}}), "already used by"),
        (lambda d: d["storeys"][0]["rooms"][0].update(floor="lava"), "unknown finish"),
    ],
)  # fmt: skip
def test_errors_are_located(change, message):
    with pytest.raises(SpecError, match=message):
        parse_plan(with_changes(change))


def test_lengths_accept_units(tmp_path):
    data = with_changes(lambda d: d["storeys"][0].update(height="2.7 m"))
    (tmp_path / "plan.yaml").write_text(yaml.safe_dump(data))
    assert load_plan(tmp_path).storeys[0].height == 2700
