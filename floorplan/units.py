"""Length parsing. The spec's canonical unit is the millimetre.

Bare numbers are millimetres. Strings may carry a unit, so surveys can be
entered as measured: "3.6 m", "360 cm", "3600 mm", "3600".
"""

import re

_UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
_LENGTH = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m)?\s*$", re.IGNORECASE)


def to_mm(value: object) -> float:
    """Convert a spec length to millimetres."""
    if isinstance(value, bool):
        raise ValueError(f"not a length: {value!r}")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = _LENGTH.match(value)
        if match:
            number, unit = match.groups()
            return float(number) * _UNIT_MM[(unit or "mm").lower()]
    raise ValueError(f"not a length: {value!r} (use a number in mm, or a string like '3.6 m')")


def to_point(value: object) -> tuple[float, float]:
    """Convert a spec point [x, y] to millimetres."""
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError(f"not a point: {value!r} (use [x, y])")
    return (to_mm(value[0]), to_mm(value[1]))


def format_area_m2(area_mm2: float) -> str:
    """Area label as Australian plans show it, e.g. '24.5 m²'."""
    return f"{area_mm2 / 1e6:.1f} m²"
