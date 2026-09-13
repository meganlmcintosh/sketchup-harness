import math

import pytest

from floorplan.geometry.storey import resolve_storey
from floorplan.roofs import resolve_roofs, roof_faces
from floorplan.spec import SpecError, parse_plan
from tests.conftest import edge_report
from tests.test_spec import with_changes

# MINIMAL is a 6000 x 4000 single storey: FFL 0, ceiling 2440.


def roofs_for(*roofs: dict):
    plan = parse_plan(with_changes(lambda d: d.update(roof=list(roofs))))
    storeys = [resolve_storey(s) for s in plan.storeys]
    return resolve_roofs(plan.roofs, storeys)


@pytest.mark.parametrize(
    "roof",
    [
        {"type": "hip"},
        {"type": "gable"},
        {"type": "gable", "ridge": "north-south"},
        {"type": "skillion", "down": "south"},
        {"type": "flat"},
        {"type": "flat", "parapet": 400},
    ],
)
def test_every_roof_type_is_watertight(roof):
    (resolved,) = roofs_for(roof)
    faces = roof_faces(resolved)
    assert faces
    assert edge_report(faces) == (0, 0)


def test_hip_ridge_height():
    (roof,) = roofs_for({"type": "hip", "pitch": 22.5, "eaves": 450, "fascia": 250})
    assert roof.eaves_z == 2440 + 250
    # Half the short side of the eaves outline (4000 + 2 * 450), at 22.5 degrees.
    expected = roof.eaves_z + math.tan(math.radians(22.5)) * (4000 + 900) / 2
    top = max(z for face in roof_faces(roof) for *_, z in face.points)
    assert top == pytest.approx(expected, abs=0.5)
    assert len(roof.pieces) == 4


def test_gable_ends_are_clad_like_the_walls():
    (roof,) = roofs_for({"type": "gable"})  # ridge runs along the longer, east-west side
    gable_faces = [f for f in roof_faces(roof) if f.finish == "face_brick"]
    assert len(gable_faces) >= 2
    assert {round(p[0]) for f in gable_faces for p in f.points} <= {-450, 6450}  # the east and west ends


def test_two_hips_make_an_l_with_a_valley():
    main = {"type": "hip", "outline": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]]}
    wing = {"type": "hip", "outline": [[3000, 0], [6000, 0], [6000, 8000], [3000, 8000]]}
    (roof,) = roofs_for(main, wing)
    faces = roof_faces(roof)
    assert edge_report(faces) == (0, 0)
    # Where the wing meets the main roof, a point on the valley line sits lower than either ridge.
    ridge = max(z for f in faces for *_, z in f.points)
    assert roof.height(3200, 3800) < ridge


def test_l_shaped_outline_becomes_two_overlapping_wings():
    l_shape = [[0, 0], [6000, 0], [6000, 2000], [3000, 2000], [3000, 4000], [0, 4000]]
    (roof,) = roofs_for({"type": "hip", "outline": l_shape})
    assert len(roof.parts) == 2  # the two maximal rectangles of an L
    assert edge_report(roof_faces(roof)) == (0, 0)
    ridge = max(z for f in roof_faces(roof) for *_, z in f.points)
    assert roof.height(3200, 2200) < ridge  # a valley at the inner corner


def test_odd_outline_is_partitioned_with_a_warning():
    bay = [[0, 0], [6000, 0], [6000, 4000], [4500, 4000], [3000, 5500], [1500, 4000], [0, 4000]]
    plan = parse_plan(with_changes(lambda d: d.update(roof=[{"type": "hip", "outline": bay}])))
    storeys = [resolve_storey(s) for s in plan.storeys]
    (roof,) = resolve_roofs(plan.roofs, storeys)
    assert len(roof.parts) >= 2
    assert edge_report(roof_faces(roof)) == (0, 0)
    assert any("convex pieces" in w for w in storeys[0].warnings)


def test_skillion_over_an_l_is_one_plane():
    l_shape = [[0, 0], [6000, 0], [6000, 2000], [3000, 2000], [3000, 4000], [0, 4000]]
    (roof,) = roofs_for({"type": "skillion", "down": "south", "outline": l_shape})
    assert len(roof.parts) == 1 and len(roof.parts[0].planes) == 1
    assert edge_report(roof_faces(roof)) == (0, 0)


def test_skillion_needs_a_low_side():
    with pytest.raises(SpecError, match="low side"):
        parse_plan(with_changes(lambda d: d.update(roof=[{"type": "skillion"}])))
