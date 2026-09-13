import math

import pytest

from floorplan.build import resolve
from floorplan.catalogue import CATALOGUE
from floorplan.furniture import place_items
from floorplan.geometry.storey import resolve_storey
from floorplan.spec import SpecError, parse_plan
from tests.conftest import EXAMPLE, edge_report
from tests.test_spec import with_changes


@pytest.mark.parametrize("kind", sorted(CATALOGUE))
def test_every_design_is_made_of_closed_parts(kind):
    design = CATALOGUE[kind].build(**CATALOGUE[kind].params)
    assert design.faces and design.symbols
    assert edge_report(design.faces) == (0, 0)
    xs = [p[0] for f in design.faces for p in f.points]
    ys = [p[1] for f in design.faces for p in f.points]
    # Parts stay inside the footprint the placement step checks against walls.
    assert min(xs) >= -design.width / 2 - 0.5 and max(xs) <= design.width / 2 + 0.5
    assert min(ys) >= -0.5 and max(ys) <= design.depth + 0.5


def items_plan(*items):
    return parse_plan(with_changes(lambda d: d["storeys"][0].update(items=list(items))))


def test_against_a_wall_faces_into_the_room():
    plan = items_plan({"type": "bed", "room": "Living", "against": "north"})
    rs = resolve_storey(plan.storeys[0])
    (bed,) = place_items(rs)
    minx, miny, maxx, maxy = bed.footprint.bounds
    room = rs.room_named("Living").polygon.bounds  # 250..5750 x 250..3750
    assert maxy == pytest.approx(room[3])  # back on the north wall
    assert (minx + maxx) / 2 == pytest.approx((room[0] + room[2]) / 2)  # centred along it
    assert bed.bearing == 180  # facing south, into the room


def test_offset_runs_from_the_west_or_south_end():
    plan = items_plan(
        {"type": "kitchen_bench", "room": "Living", "against": "north", "offset": 500, "length": 2000},
        {"type": "kitchen_bench", "room": "Living", "against": "east", "offset": 300, "length": 1200},
    )
    rs = resolve_storey(plan.storeys[0])
    north, east = place_items(rs)
    assert north.footprint.bounds[0] == pytest.approx(250 + 500)
    assert east.footprint.bounds[1] == pytest.approx(250 + 300)


def test_sink_offset_is_mirrored_for_a_south_facing_bench():
    # Against a north wall the bench faces south, so its local +x points west; the
    # sink offset must still be measured from the west end.
    design_south = CATALOGUE["kitchen_bench"].build(length=3000, sink=500, start=-1)
    design_north = CATALOGUE["kitchen_bench"].build(length=3000, sink=500, start=1)
    steel = lambda d: [p[0] for f in d.faces if f.finish == "appliance_steel" for p in f.points]  # noqa: E731
    assert (min(steel(design_north)) + max(steel(design_north))) / 2 == pytest.approx(-1000)
    assert (min(steel(design_south)) + max(steel(design_south))) / 2 == pytest.approx(1000)


def test_at_places_the_centre_with_a_facing():
    plan = items_plan({"type": "sofa", "at": [3000, 2000], "facing": "east"})
    (sofa,) = place_items(resolve_storey(plan.storeys[0]))
    centre = sofa.footprint.centroid
    assert (centre.x, centre.y) == pytest.approx((3000, 2000))
    minx, miny, maxx, maxy = sofa.footprint.bounds
    assert math.isclose(maxy - miny, sofa.design.width) and math.isclose(maxx - minx, sofa.design.depth)


def test_bad_items_are_rejected_or_flagged():
    with pytest.raises(SpecError, match="unknown item"):
        place_items(resolve_storey(items_plan({"type": "hot_tub", "at": [0, 0]}).storeys[0]))
    with pytest.raises(SpecError, match="unknown key"):
        place_items(resolve_storey(items_plan({"type": "bed", "at": [0, 0], "colour": "red"}).storeys[0]))
    with pytest.raises(SpecError, match="not one of"):
        place_items(resolve_storey(items_plan({"type": "bed", "at": [0, 0], "size": "huge"}).storeys[0]))
    rs = resolve_storey(items_plan({"type": "sofa", "at": [300, 2000], "facing": "east"}).storeys[0])
    place_items(rs)
    assert any("runs into a wall" in w for w in rs.warnings)


def test_example_furniture_fits():
    resolved = resolve(EXAMPLE)
    assert sum(len(v) for v in resolved.items.values()) > 30
    assert not [w for rs in resolved.storeys for w in rs.warnings]
