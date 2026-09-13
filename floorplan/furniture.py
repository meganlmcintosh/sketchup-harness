"""Placing catalogue items (furniture, joinery, fixtures) in a storey.

Two ways to place an item:

- `room` + `against: <side>`: its back goes on the room's wall facing that
  way (north/south/east/west, or a compass bearing for an angled wall), and
  it faces into the room. It is centred along that wall unless `offset`
  gives the distance from the wall's start end (its west end, or its south
  end for a wall running north-south) to the item's nearest edge. `gap`
  holds it off the wall.
- `at: [x, y]` + `facing`: its centre at that point, its front facing that way.

Offsets inside an item (a kitchen bench's `sink`) also run from the start
end, so they read west-to-east or south-to-north whichever way the item faces.
"""

import math
from dataclasses import dataclass

import shapely
from shapely.geometry import Polygon

from .catalogue import BOOL_PARAMS, CATALOGUE, CHOICE_PARAMS, INT_PARAMS, LENGTH_PARAMS, START_SENSITIVE, Design
from .geometry.storey import ResolvedRoom, ResolvedStorey
from .spec import COMPASS, SpecError
from .units import to_mm, to_point

PLACEMENT_KEYS = {"type", "at", "facing", "room", "against", "offset", "gap"}
WALL_TOLERANCE = math.cos(math.radians(45))  # a wall counts as facing a direction within this


@dataclass
class PlacedItem:
    kind: str
    design: Design
    key: tuple  # identical keys share one component
    origin: tuple[float, float]  # plan position of the item's back-centre
    bearing: float  # compass direction its front faces
    footprint: Polygon
    where: str

    @property
    def rotation(self) -> float:
        """DXF insert rotation: turns local +y (the front) to the bearing."""
        return -self.bearing


def _frame(bearing: float) -> tuple[tuple[float, float], tuple[float, float]]:
    theta = math.radians(bearing)
    front = (math.sin(theta), math.cos(theta))
    right = (math.cos(theta), -math.sin(theta))  # local +x
    return right, front


def _bearing(value, where: str) -> float:
    if isinstance(value, str) and value.lower() in COMPASS:
        return COMPASS[value.lower()]
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value) % 360
    raise SpecError(where, "north, east, south, west, or a compass bearing in degrees")


def _params(kind: str, raw: dict, here: str) -> dict:
    entry = CATALOGUE[kind]
    params = {}
    for name, default in entry.params.items():
        value = raw.get(name, default)
        where = f"{here}.{name}"
        if value is None:
            params[name] = None
        elif name in LENGTH_PARAMS:
            try:
                params[name] = to_mm(value)
            except ValueError as exc:
                raise SpecError(where, str(exc)) from None
        elif name in INT_PARAMS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SpecError(where, "a whole number")
            params[name] = value
        elif name in BOOL_PARAMS:
            if not isinstance(value, bool):
                raise SpecError(where, "true or false")
            params[name] = value
        elif name in CHOICE_PARAMS:
            if value not in CHOICE_PARAMS[name]:
                raise SpecError(where, f"'{value}' is not one of {list(CHOICE_PARAMS[name])}")
            params[name] = value
    return params


@dataclass
class WallEdge:
    """A straight run of a room's boundary, seen from inside."""

    start: tuple[float, float]  # the west end, or the south end of a north-south wall
    end: tuple[float, float]
    inward: tuple[float, float]  # unit normal into the room

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def bearing(self) -> float:
        """Compass direction an item against this wall faces."""
        return math.degrees(math.atan2(self.inward[0], self.inward[1])) % 360


def room_wall(room: ResolvedRoom, side_bearing: float) -> WallEdge | None:
    """The longest boundary edge of a room whose outside faces `side_bearing`."""
    outward = (math.sin(math.radians(side_bearing)), math.cos(math.radians(side_bearing)))
    ring = list(shapely.orient_polygons(shapely.simplify(room.polygon, 0.5)).exterior.coords)
    best = None
    for (x0, y0), (x1, y1) in zip(ring, ring[1:], strict=False):
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1:
            continue
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = uy, -ux  # right of a counter-clockwise ring: outward
        if nx * outward[0] + ny * outward[1] < WALL_TOLERANCE:
            continue
        a, b = (x0, y0), (x1, y1)
        if (abs(ux) >= abs(uy) and a[0] > b[0]) or (abs(ux) < abs(uy) and a[1] > b[1]):
            a, b = b, a  # start at the west end, or the south end
        if best is None or length > best.length:
            best = WallEdge(a, b, (-nx, -ny))
    return best


def _build(kind: str, params: dict, start: int, where: str) -> Design:
    try:
        return CATALOGUE[kind].build(**params, start=start)
    except ValueError as exc:
        raise SpecError(where, str(exc)) from None


def place_items(rs: ResolvedStorey) -> list[PlacedItem]:
    placed: list[PlacedItem] = []
    for j, raw in enumerate(rs.storey.items):
        here = f"{rs.storey.where}.items[{j}]"
        if not isinstance(raw, dict):
            raise SpecError(here, "expected a mapping")
        kind = raw.get("type")
        if kind not in CATALOGUE:
            raise SpecError(f"{here}.type", f"unknown item '{kind}'; known: {sorted(CATALOGUE)}")
        allowed = PLACEMENT_KEYS | set(CATALOGUE[kind].params)
        extra = sorted(set(raw) - allowed)
        if extra:
            raise SpecError(here, f"unknown key(s) {extra} for {kind}; allowed: {sorted(allowed)}")
        params = _params(kind, raw, here)
        try:
            gap = to_mm(raw.get("gap", 0))
            offset = to_mm(raw["offset"]) if "offset" in raw else None
        except ValueError as exc:
            raise SpecError(here, str(exc)) from None

        room = None
        if "room" in raw:
            room = rs.room_named(raw["room"])
            if room is None:
                raise SpecError(f"{here}.room", f"no room '{raw['room']}' on {rs.storey.name}")

        if "against" in raw and "at" in raw:
            raise SpecError(here, "place an item with 'at' or with 'room' + 'against', not both")
        if "against" not in raw and offset is not None:
            raise SpecError(f"{here}.offset", "'offset' goes with 'against'; with 'at' the position is the centre")

        if "against" in raw:
            if room is None:
                raise SpecError(here, "'against' needs a 'room'")
            side = _bearing(raw["against"], f"{here}.against")
            wall = room_wall(room, side)
            if wall is None:
                raise SpecError(f"{here}.against", f"{room.room.name} has no wall facing {raw['against']}")
            bearing = wall.bearing
            right, front = _frame(bearing)
            # The wall's start end is on the item's local -x side when the wall
            # runs the same way as local +x; offsets along the item then run from it.
            ux, uy = (wall.end[0] - wall.start[0]) / wall.length, (wall.end[1] - wall.start[1]) / wall.length
            start = 1 if ux * right[0] + uy * right[1] > 0 else -1
            design = _build(kind, params, start, here)
            along = offset + design.width / 2 if offset is not None else wall.length / 2
            if offset is not None and along + design.width / 2 > wall.length + 0.5:
                rs.warnings.append(f"{here}: {kind} runs past the end of the wall")
            origin = (
                wall.start[0] + ux * along + front[0] * gap,
                wall.start[1] + uy * along + front[1] * gap,
            )
        else:
            if "at" not in raw:
                raise SpecError(here, "place an item with 'at: [x, y]', or 'room' + 'against'")
            bearing = _bearing(raw.get("facing", "north"), f"{here}.facing")
            start = 1
            design = _build(kind, params, start, here)
            cx, cy = to_point(raw["at"])
            _, front = _frame(bearing)
            origin = (cx - front[0] * design.depth / 2, cy - front[1] * design.depth / 2)

        right, front = _frame(bearing)
        corners = [(origin[0] + right[0] * u + front[0] * v, origin[1] + right[1] * u + front[1] * v)
                   for u, v in ((-design.width / 2, 0), (design.width / 2, 0),
                                (design.width / 2, design.depth), (-design.width / 2, design.depth))]  # fmt: skip
        footprint = Polygon(corners)
        key = (kind, tuple(sorted(params.items())), start if kind in START_SENSITIVE else 0)
        item = PlacedItem(kind, design, key, origin, bearing, footprint, here)

        if room is not None and not room.polygon.buffer(2).covers(footprint):
            rs.warnings.append(f"{here}: {kind} extends outside {room.room.name}")
        if footprint.intersection(rs.walls).area > 1_000:
            rs.warnings.append(f"{here}: {kind} runs into a wall")
        placed.append(item)
    return placed
