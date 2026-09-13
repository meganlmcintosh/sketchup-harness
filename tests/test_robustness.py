"""Geometry at awkward angles and shapes must still come out watertight.

These are the cases an adversarial review broke before the kernel was moved
to a single planar arrangement per solid: anything not axis-aligned leaked."""

import math
import random

import pytest

from floorplan.geometry.storey import resolve_storey
from floorplan.model3d import structure_faces
from floorplan.roofs import resolve_roofs, roof_faces
from floorplan.spec import parse_plan
from floorplan.stairs import balustrade_faces, resolve_stairs, stair_faces
from tests.conftest import edge_report

BOX = [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]
BIG = [[0, 0], [8000, 0], [8000, 8000], [0, 8000]]
L_SHAPE = [[0, 0], [8000, 0], [8000, 4000], [4000, 4000], [4000, 8000], [0, 8000]]


def rotated(points, degrees):
    t = math.radians(degrees)
    c, s = math.cos(t), math.sin(t)
    return [[round(x * c - y * s, 3), round(x * s + y * c, 3)] for x, y in points]


def turn(x, y, degrees):
    return rotated([[x, y]], degrees)[0]


def house(points, rooms, openings=(), walls=(), stairs=(), name="Ground"):
    ext = {"id": f"{name}-EXT", "type": "brick_veneer", "closed": True, "align": "outside", "points": points}
    return {"name": name, "walls": [ext, *walls], "rooms": rooms, "openings": list(openings), "stairs": list(stairs)}


def rotated_house(degrees):
    openings = [
        {"type": "door", "at": turn(3000, 0, degrees)},
        {"type": "window", "at": turn(1500, 4000, degrees)},
        {"type": "window", "at": turn(6000, 2000, degrees), "width": 1810},
    ]
    return house(rotated(BOX, degrees), [{"name": "Living", "at": turn(3000, 2000, degrees)}], openings)


@pytest.mark.parametrize("degrees", [5, 17, 30, 45, 61, 90, 123, 200, 271, 333])
def test_rotated_house_with_openings_is_watertight(degrees):
    rs = resolve_storey(parse_plan({"storeys": [rotated_house(degrees)]}).storeys[0])
    assert edge_report(structure_faces(rs, None)) == (0, 0)


@pytest.mark.parametrize("degrees", [5, 30, 45, 80])
def test_angled_internal_wall_with_a_door(degrees):
    cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    wall = {"type": "stud_internal", "points": [[250, 250], [250 + 3000 * cos, 250 + 3000 * sin]]}
    door = {"type": "door", "at": [250 + 1500 * cos, 250 + 1500 * sin]}
    storey = house(BOX, [{"name": "Living", "at": [5000, 3500]}], [door], walls=[wall])
    rs = resolve_storey(parse_plan({"storeys": [storey]}).storeys[0])
    assert edge_report(structure_faces(rs, None)) == (0, 0)


@pytest.mark.parametrize("kind", ["straight", "l_shaped", "u_shaped"])
@pytest.mark.parametrize("bearing", [0, 45, 137.5, 200, 289])
@pytest.mark.parametrize("side", ["left", "right"])
def test_stairs_at_any_bearing(kind, bearing, side):
    stair = {"type": kind, "start": [4000, 4000], "direction": bearing, "width": 900, "turn": side}
    ground = house(BIG, [{"name": "L", "at": [7000, 7000]}], stairs=[stair])
    upper = house(BIG, [{"name": "Up", "at": [500, 500]}], name="Upper")
    storeys = [resolve_storey(s) for s in parse_plan({"storeys": [ground, upper]}).storeys]
    (resolved,) = resolve_stairs(storeys)
    assert edge_report(stair_faces(resolved)) == (0, 0)
    assert edge_report(balustrade_faces([resolved])) == (0, 0)
    assert edge_report(structure_faces(storeys[1], storeys[0])) == (0, 0)


def roof_over(outline, roof):
    storey = house(BOX, [{"name": "L", "at": [3000, 2000]}])
    plan = parse_plan({"storeys": [storey], "roof": [{**roof, "outline": outline}]})
    storeys = [resolve_storey(s) for s in plan.storeys]
    (rr,) = resolve_roofs(plan.roofs, storeys)
    return rr, roof_faces(rr)


def surface_deviation(rr, faces):
    """How far roof-plane vertices sit from the surface the parts define."""
    return max(abs(z - rr.height(x, y)) for f in faces if f.finish == "roof_dark" for x, y, z in f.points)


@pytest.mark.parametrize("degrees", [0.5, 6, 30, 45, 72, 111, 150])
@pytest.mark.parametrize("kind", ["hip", "gable"])
def test_rotated_roofs_lie_on_their_planes(degrees, kind):
    rr, faces = roof_over(rotated(BOX, degrees), {"type": kind})
    assert edge_report(faces) == (0, 0)
    assert surface_deviation(rr, faces) < 1.0


@pytest.mark.parametrize("degrees", [0, 12, 30, 45, 100])
def test_rotated_l_is_still_two_wings(degrees):
    rr, faces = roof_over(rotated(L_SHAPE, degrees), {"type": "hip"})
    assert len(rr.parts) == 2
    assert edge_report(faces) == (0, 0)


@pytest.mark.parametrize("sides", [3, 5, 6, 7, 8, 12])
def test_regular_polygon_hips_meet_at_the_apex(sides):
    step = 2 * math.pi / sides
    poly = [[round(3000 + 3000 * math.cos(i * step), 3), round(3000 + 3000 * math.sin(i * step), 3)]
            for i in range(sides)]  # fmt: skip
    rr, faces = roof_over(poly, {"type": "hip"})
    assert edge_report(faces) == (0, 0)
    assert surface_deviation(rr, faces) < 1.0
    assert len(rr.parts[0].planes) == sides


@pytest.mark.parametrize(
    "outline",
    [
        [[0, 0], [5000, 0], [5000, 4999], [0, 4999]],  # a 1 mm ridge
        [[0, 0], [3000, 0], [3000, 1], [6000, 1], [6000, 4000], [0, 4000]],  # a 1 mm jog
        [[0.123, 0.456], [6000.789, 0.001], [6000.333, 4000.777], [0.05, 4000.05]],  # off the grid
    ],
)
def test_awkward_outlines(outline):
    _, faces = roof_over(outline, {"type": "hip"})
    assert edge_report(faces) == (0, 0)


def test_a_step_between_parts_is_closed():
    hip = {"type": "hip", "outline": BOX}
    wing = [[6000, 0], [9000, 0], [9000, 4000], [6000, 4000]]
    lean_to = {"type": "skillion", "down": "south", "eaves": 0, "outline": wing}
    plan = parse_plan({"storeys": [house(BOX, [{"name": "L", "at": [3000, 2000]}])], "roof": [hip, lean_to]})
    storeys = [resolve_storey(s) for s in plan.storeys]
    (rr,) = resolve_roofs(plan.roofs, storeys)
    assert edge_report(roof_faces(rr)) == (0, 0)


def test_random_rotations_never_leak():
    rng = random.Random(7)
    for _ in range(12):
        degrees = rng.uniform(0, 360)
        rs = resolve_storey(parse_plan({"storeys": [rotated_house(degrees)]}).storeys[0])
        assert edge_report(structure_faces(rs, None)) == (0, 0), degrees
