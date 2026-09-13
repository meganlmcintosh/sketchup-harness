import pytest

from floorplan.units import format_area_m2, to_mm, to_point


@pytest.mark.parametrize(
    ("value", "expected"),
    [(3600, 3600.0), (2.5, 2.5), ("3600", 3600.0), ("3600 mm", 3600.0), ("360cm", 3600.0), ("3.6 m", 3600.0),
     (" 1.25M ", 1250.0), ("-450", -450.0)],
)  # fmt: skip
def test_to_mm(value, expected):
    assert to_mm(value) == expected


@pytest.mark.parametrize("value", [True, None, "3.6 metres", "3,600", [3600], "ft"])
def test_to_mm_rejects(value):
    with pytest.raises(ValueError):
        to_mm(value)


def test_to_point_and_area():
    assert to_point(["1.2 m", 300]) == (1200.0, 300.0)
    with pytest.raises(ValueError):
        to_point([1, 2, 3])
    assert format_area_m2(24_540_000) == "24.5 m²"
