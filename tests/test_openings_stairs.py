from collections import Counter

import pytest

from floorplan.build import resolve
from floorplan.geometry.storey import resolve_storey
from floorplan.model3d import structure_faces
from floorplan.openings3d import build_units
from floorplan.spec import SpecError, parse_plan
from floorplan.stairs import balustrade_faces, resolve_stairs, stair_faces
from tests.conftest import EXAMPLE, edge_report
from tests.test_spec import with_changes


def two_storeys(stair: dict, upper_walls=None) -> dict:
    """The minimal plan plus a storey above it, with a stair from the ground floor."""

    def change(d):
        ground = d["storeys"][0]
        ground["stairs"] = [stair]
        ground["openings"] = []
        d["storeys"].append({
            "name": "Upper",
            "walls": upper_walls or [{**ground["walls"][0], "id": "UP-EXT"}],
            "rooms": [{"name": "Landing", "at": [500, 500]}],
        })  # fmt: skip

    return with_changes(change)


def test_units_are_closed_solids_and_shared():
    resolved = resolve(EXAMPLE)
    units = {}
    total = 0
    for rs in resolved.storeys:
        placements = build_units(rs.openings, rs.storey.level, units)
        assert len(placements) == len(rs.openings)
        total += len(placements)
    assert len(units) < total  # identical doors share one component, across storeys too
    labels = [u.label for u in units.values()]
    assert len(set(labels)) == len(labels), "every distinct design has a distinct name"
    for unit in units.values():
        # Each part is closed on its own, so the whole unit is too.
        assert edge_report(unit.faces) == (0, 0), unit.block


def test_a_door_opening_the_other_way_is_the_same_unit_turned_round():
    resolved = resolve(EXAMPLE)
    ground = resolved.storeys[0]
    units = {}
    placements = build_units(ground.openings, 0.0, units)
    by_block = {}
    for placed, placement in zip([o for o in ground.openings if o.opening.kind != "opening"], placements, strict=True):
        by_block.setdefault(placement.block, set()).add(placed.side)
    two_sided = [block for block, sides in by_block.items() if sides == {1, -1}]
    assert two_sided, "the example has the same door opening both ways"
    rotations = {round(p.rotation) % 180 for p in placements if p.block == two_sided[0]}
    assert len(rotations) <= 2  # along the wall, or along it turned 180


def test_example_stair_follows_limits():
    resolved = resolve(EXAMPLE)
    (stair,) = resolved.stairs
    assert (stair.risers, round(stair.riser, 1)) == (17, 176.5)
    assert 550 <= 2 * stair.riser + stair.stair.going <= 700
    assert not stair.warnings
    assert edge_report(stair_faces(stair)) == (0, 0)
    assert edge_report(balustrade_faces([stair])) == (0, 0)


def test_void_is_cut_from_the_floor_above_and_not_counted_as_area():
    resolved = resolve(EXAMPLE)
    lower, upper = resolved.storeys
    stair = resolved.stairs[0]
    assert upper.voids and upper.voids[0].area == pytest.approx(stair.void.area)
    hall = upper.room_named("Hall")
    assert hall.area == pytest.approx(hall.polygon.area - stair.void.area)
    assert edge_report(structure_faces(upper, lower)) == (0, 0)


@pytest.mark.parametrize("kind", ["l_shaped", "u_shaped"])
def test_turning_stairs_are_closed_and_rise_fully(kind):
    stair = {"type": kind, "start": [4500, 600], "direction": "north", "width": 900, "turn": "left"}
    plan = parse_plan(two_storeys(stair))
    storeys = [resolve_storey(s) for s in plan.storeys]
    (resolved,) = resolve_stairs(storeys)
    tops = [t.top for t in resolved.treads]
    assert tops == sorted(tops) and len(tops) == resolved.risers - 1
    assert edge_report(stair_faces(resolved)) == (0, 0)
    directions = Counter((round(t.direction[0]), round(t.direction[1])) for t in resolved.treads)
    assert len(directions) == 2  # two flights at an angle (the landing counts with the first)


def test_stair_needs_a_storey_above():
    data = with_changes(lambda d: d["storeys"][0].update(stairs=[{"start": [1000, 1000], "direction": "east"}]))
    storeys = [resolve_storey(s) for s in parse_plan(data).storeys]
    with pytest.raises(SpecError, match="storey above"):
        resolve_stairs(storeys)


def test_bad_direction_is_rejected():
    data = with_changes(lambda d: d["storeys"][0].update(stairs=[{"start": [1000, 1000], "direction": "up"}]))
    with pytest.raises(SpecError, match="compass bearing"):
        parse_plan(data)
