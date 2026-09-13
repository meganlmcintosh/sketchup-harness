import pytest
from shapely.geometry import Polygon, box

from floorplan.build import resolve
from floorplan.geometry.solid import Prism, build_solid, triangulate
from floorplan.geometry.storey import resolve_storey
from floorplan.model3d import structure_faces
from floorplan.spec import SpecError, parse_plan
from tests.conftest import EXAMPLE, edge_report
from tests.test_spec import MINIMAL, with_changes


def plain(*_args):
    return "paint_white"


def split_nothing(region, _z, _up):
    return [(region, "paint_white")]


def test_box_is_closed():
    faces = build_solid([Prism(box(0, 0, 1000, 500), 0, 300)], [], split_nothing, plain)
    assert edge_report(faces) == (0, 0)


def test_wall_with_window_has_no_t_junctions():
    wall = box(0, 0, 3000, 110)
    window = box(1050, -5, 1950, 115)
    faces = build_solid([Prism(wall, 0, 2400)], [Prism(window, 900, 2100)], split_nothing, plain)
    assert edge_report(faces) == (0, 0)


def test_touching_prisms_merge_and_stay_closed():
    slab = Prism(box(0, 0, 4000, 3000), -300, 0)
    walls = Prism(box(0, 0, 4000, 3000).difference(box(250, 250, 3750, 2750)), 0, 2400)
    door = Prism(box(1500, -5, 2380, 255), 0, 2100)
    faces = build_solid([slab, walls], [door], split_nothing, plain)
    assert edge_report(faces) == (0, 0)


def test_triangulate_keeps_collinear_vertices():
    poly = Polygon([(0, 0), (500, 0), (1000, 0), (1000, 400), (1000, 1000), (0, 1000)],
                   [[(200, 200), (200, 400), (400, 400), (400, 200)]])  # fmt: skip
    used = {p for tri in triangulate(poly) for p in tri}
    assert {(500.0, 0.0), (1000.0, 400.0)} <= used
    assert sum(abs(Polygon(t).area) for t in triangulate(poly)) == pytest.approx(poly.area)


def test_example_rooms_and_doors():
    ground, first = resolve(EXAMPLE).storeys
    areas = {r.room.name: round(r.area / 1e6, 1) for r in ground.rooms}
    assert areas == {
        "Porch": 3.0, "Study": 13.7, "Entry": 13.9, "Laundry": 3.9, "WC": 2.8, "Kitchen / Living / Dining": 57.8,
    }  # fmt: skip
    assert not ground.unnamed and not first.unnamed

    def opens_into(rs, at):
        placed = next(o for o in rs.openings if o.opening.at == at)
        probe = placed.segment.point(placed.along, placed.side * (placed.segment.thickness / 2 + 150))
        room = rs.room_at(probe)
        return room.room.name if room else "outside"

    assert opens_into(ground, (6000.0, 0.0)) == "Entry"  # external doors open inwards
    assert opens_into(ground, (2500.0, 6600.0)) == "Kitchen / Living / Dining"  # WC door opens out
    assert opens_into(first, (3500.0, 4500.0)) == "Bed 2"  # into the smaller room
    assert opens_into(first, (5000.0, 9300.0)) == "Bed 1"  # explicit `into`


def test_example_structure_is_watertight():
    storeys = resolve(EXAMPLE).storeys
    for i, rs in enumerate(storeys):
        faces = structure_faces(rs, storeys[i - 1] if i else None)
        assert edge_report(faces) == (0, 0), rs.storey.name


def test_opening_past_wall_end_is_rejected():
    window = {"type": "window", "at": [5900, 0], "width": 1810}
    data = with_changes(lambda d: d["storeys"][0]["openings"].append(window))
    with pytest.raises(SpecError, match="runs into a corner or past the end"):
        resolve_storey(parse_plan(data).storeys[0])


def test_room_outside_walls_is_rejected():
    data = with_changes(lambda d: d["storeys"][0]["rooms"].append({"name": "Garden", "at": [9000, 9000]}))
    with pytest.raises(SpecError, match="not inside an enclosed area"):
        resolve_storey(parse_plan(data).storeys[0])


def test_align_outside_keeps_overall_size():
    rs = resolve_storey(parse_plan(MINIMAL).storeys[0])
    assert rs.shell.bounds == (0.0, 0.0, 6000.0, 4000.0)
    assert rs.rooms[0].polygon.bounds == (250.0, 250.0, 5750.0, 3750.0)
