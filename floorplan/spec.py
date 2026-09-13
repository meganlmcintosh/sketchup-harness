"""Load plan.yaml and validate it into typed objects.

Validation here is structural: types, references, required fields. Geometric
checks (does an opening sit in a wall, is a room enclosed) happen when the
storey is resolved, in geometry/storey.py.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from shapely.geometry import LineString, Polygon

from . import au_defaults as au
from .units import to_mm, to_point


class SpecError(ValueError):
    """A problem in plan.yaml, located by a path like storeys[0].walls[2]."""

    def __init__(self, where: str, message: str):
        super().__init__(f"{where}: {message}")
        self.where = where


@dataclass(frozen=True)
class Finish:
    key: str
    name: str
    rgb: tuple[int, int, int]
    alpha: float = 1.0


@dataclass(frozen=True)
class WallType:
    key: str
    thickness: float
    outside: str
    inside: str


@dataclass
class Wall:
    id: str
    type: WallType
    points: list[tuple[float, float]]
    closed: bool
    align: str  # centre | left | right | inside | outside
    where: str


@dataclass
class Opening:
    kind: str
    width: float  # leaf width for hinged doors, frame width otherwise
    height: float  # leaf height for hinged doors, frame height otherwise
    sill: float  # bottom of the hole, above FFL
    head: float  # top of the hole, above FFL
    at: tuple[float, float] | None
    wall: str | None
    offset: float | None
    into: str | None  # room name a door swings or slides into ("outside" allowed)
    hinge: str  # left | right, seen from the room the door swings into
    where: str

    @property
    def is_door(self) -> bool:
        return self.kind != "window"

    @property
    def hole_width(self) -> float:
        extra = 2 * au.DOOR_FRAME if self.kind in au.HINGED_DOORS else 0.0
        return self.width + extra


@dataclass
class Room:
    name: str
    at: tuple[float, float]
    floor: str
    walls: str
    ceiling: str
    label_at: tuple[float, float] | None
    where: str


COMPASS = {"north": 0.0, "east": 90.0, "south": 180.0, "west": 270.0}


@dataclass
class Stair:
    kind: str  # straight | l_shaped | u_shaped
    start: tuple[float, float]  # centre of the bottom riser
    bearing: float  # compass degrees you face walking up: 0 north, 90 east
    width: float
    going: float  # tread depth
    turn: str  # left | right, for l_shaped and u_shaped
    landing_at: int | None  # risers before the landing
    gap: float  # between the two flights of a u_shaped stair
    finish: str
    where: str


@dataclass
class Roof:
    kind: str  # hip | gable | skillion | flat
    over: str  # storey whose ceiling the roof sits on
    outline: list[tuple[float, float]] | None  # plan outline before eaves; None: the storey's walls
    pitch: float  # degrees
    eaves: float  # overhang past the outline
    fascia: float  # depth of the fascia band under the roof planes
    ridge: str | float | None  # gable: east-west | north-south | a compass bearing; None: along the longest side
    down: str | None  # skillion: the low side, as a compass direction
    parapet: float  # flat roofs: parapet height above the roof
    finish: str
    where: str


@dataclass
class Storey:
    index: int
    name: str
    level: float  # FFL above datum
    height: float  # FFL to ceiling
    floor: float  # structure thickness below FFL
    walls: list[Wall]
    openings: list[Opening]
    rooms: list[Room]
    separators: list[list[tuple[float, float]]]
    slab_extensions: list[list[tuple[float, float]]]
    items: list[dict] = field(default_factory=list)
    stairs: list[Stair] = field(default_factory=list)
    where: str = ""

    @property
    def key(self) -> str:
        """Short stable id used in DXF layer and block names."""
        return f"S{self.index + 1}"


@dataclass
class Plan:
    name: str
    project: dict
    settings: dict
    finishes: dict[str, Finish]
    wall_types: dict[str, WallType]
    storeys: list[Storey]
    roofs: list[Roof]
    source: Path | None = None

    def finish(self, key: str) -> Finish:
        return self.finishes[key]


# --- helpers -----------------------------------------------------------------


def _mapping(value, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SpecError(where, f"expected a mapping, got {type(value).__name__}")
    return value


def _list(value, where: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(where, f"expected a list, got {type(value).__name__}")
    return value


def _unknown_keys(data: dict, allowed: set[str], where: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise SpecError(where, f"unknown key(s) {extra}; allowed: {sorted(allowed)}")


def _length(data: dict, key: str, where: str, default=None) -> float:
    if key not in data or data[key] is None:
        if default is None:
            raise SpecError(where, f"'{key}' is required")
        return float(default)
    try:
        return to_mm(data[key])
    except ValueError as exc:
        raise SpecError(f"{where}.{key}", str(exc)) from None


def _point(value, where: str) -> tuple[float, float]:
    try:
        return to_point(value)
    except ValueError as exc:
        raise SpecError(where, str(exc)) from None


def _points(value, where: str, minimum: int) -> list[tuple[float, float]]:
    pts = [_point(p, f"{where}[{i}]") for i, p in enumerate(_list(value, where))]
    if len(pts) < minimum:
        raise SpecError(where, f"needs at least {minimum} points, got {len(pts)}")
    return pts


def _choice(data: dict, key: str, options: tuple[str, ...], where: str, default: str) -> str:
    value = data.get(key, default)
    if value not in options:
        raise SpecError(f"{where}.{key}", f"'{value}' is not one of {list(options)}")
    return value


# --- sections ----------------------------------------------------------------


def _finishes(data, where: str) -> dict[str, Finish]:
    merged = {k: dict(v) for k, v in au.FINISHES.items()}
    for key, value in _mapping(data, where).items():
        value = _mapping(value, f"{where}.{key}")
        _unknown_keys(value, {"name", "rgb", "alpha"}, f"{where}.{key}")
        merged[key] = {**merged.get(key, {}), **value}

    finishes = {}
    for key, value in merged.items():
        rgb = value.get("rgb")
        if not (isinstance(rgb, list | tuple) and len(rgb) == 3 and all(0 <= int(c) <= 255 for c in rgb)):
            raise SpecError(f"{where}.{key}.rgb", "expected [r, g, b] with values 0-255")
        name = value.get("name") or key.replace("_", " ").title()
        alpha = value.get("alpha", 1.0)
        if isinstance(alpha, bool) or not isinstance(alpha, int | float) or not 0 < alpha <= 1:
            raise SpecError(f"{where}.{key}.alpha", "opacity from 0 (invisible) to 1 (solid)")
        finishes[key] = Finish(key, str(name), tuple(int(c) for c in rgb), float(alpha))

    # SketchUp's importer makes one material per colour, so colours must be unique.
    seen: dict[tuple[int, int, int], str] = {}
    for key, finish in finishes.items():
        if finish.rgb in seen:
            raise SpecError(
                f"{where}.{key}.rgb",
                f"{list(finish.rgb)} is already used by '{seen[finish.rgb]}'; "
                "each finish needs a distinct colour (nudge one value by 1)",
            )
        seen[finish.rgb] = key
    return finishes


def _wall_types(data, finishes: dict[str, Finish], where: str) -> dict[str, WallType]:
    merged = {k: dict(v) for k, v in au.WALL_TYPES.items()}
    for key, value in _mapping(data, where).items():
        value = _mapping(value, f"{where}.{key}")
        _unknown_keys(value, {"thickness", "outside", "inside"}, f"{where}.{key}")
        merged[key] = {**merged.get(key, {}), **value}

    types = {}
    for key, value in merged.items():
        here = f"{where}.{key}"
        thickness = _length(value, "thickness", here)
        if thickness <= 0:
            raise SpecError(f"{here}.thickness", "must be positive")
        for side in ("outside", "inside"):
            if value.get(side) not in finishes:
                raise SpecError(f"{here}.{side}", f"unknown finish '{value.get(side)}'")
        types[key] = WallType(key, thickness, value["outside"], value["inside"])
    return types


def _wall_points(value, where: str, closed: bool) -> list[tuple[float, float]]:
    """A wall path with repeated points dropped, checked to be a usable line or ring."""
    raw = _points(value, where, 3 if closed else 2)
    points = [raw[0]]
    for p in raw[1:]:
        if math.dist(p, points[-1]) >= 1.0:
            points.append(p)
    if closed and len(points) > 1 and math.dist(points[0], points[-1]) < 1.0:
        points.pop()  # a ring given with its first point repeated at the end
    if len(points) < (3 if closed else 2):
        raise SpecError(where, "the points are all in the same place")
    if closed:
        ring = Polygon(points)
        if not ring.is_valid or ring.area < 1.0:
            raise SpecError(where, "a closed wall must outline a simple shape: no crossings, not all in a line")
    elif len(points) > 2 and not LineString(points).is_simple:
        raise SpecError(where, "the wall crosses itself")
    return points


def _walls(data, wall_types: dict[str, WallType], where: str, used_ids: set[str]) -> list[Wall]:
    walls = []
    for i, raw in enumerate(_list(data, where)):
        here = f"{where}[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, {"id", "type", "points", "closed", "align"}, here)
        type_key = raw.get("type")
        if type_key not in wall_types:
            raise SpecError(f"{here}.type", f"unknown wall type '{type_key}'; known: {sorted(wall_types)}")
        closed = bool(raw.get("closed", False))
        points = _wall_points(raw.get("points"), f"{here}.points", closed)
        aligns = ("centre", "inside", "outside") if closed else ("centre", "left", "right")
        align = _choice(raw, "align", aligns, here, "centre")
        wall_id = str(raw.get("id") or f"W{len(used_ids) + 1}")
        if wall_id in used_ids:
            raise SpecError(f"{here}.id", f"duplicate wall id '{wall_id}'")
        used_ids.add(wall_id)
        walls.append(Wall(wall_id, wall_types[type_key], points, closed, align, here))
    return walls


_OPENING_KEYS = {"type", "at", "wall", "offset", "width", "height", "sill", "head", "into", "hinge"}


def _openings(data, wall_ids: set[str], where: str) -> list[Opening]:
    openings = []
    for i, raw in enumerate(_list(data, where)):
        here = f"{where}[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, _OPENING_KEYS, here)
        kind = raw.get("type")
        if kind not in au.OPENINGS:
            raise SpecError(f"{here}.type", f"unknown opening type '{kind}'; known: {sorted(au.OPENINGS)}")
        defaults = au.OPENINGS[kind]
        width = _length(raw, "width", here, defaults["width"])
        height = _length(raw, "height", here, defaults["height"])
        for key, value in (("width", width), ("height", height)):
            if value < 100:
                raise SpecError(f"{here}.{key}", f"{value:.0f} is too small for a {kind}; sizes are in mm")

        if kind == "window":
            if "sill" in raw and "head" in raw:
                raise SpecError(here, "give a window 'sill' or 'head', not both")
            if "sill" in raw:
                sill = _length(raw, "sill", here)
                head = sill + height
            else:
                head = _length(raw, "head", here, defaults["head"])
                sill = head - height
            if sill < 0:
                raise SpecError(here, f"window sill would be {sill:.0f} below the floor")
        else:
            if "sill" in raw:
                raise SpecError(f"{here}.sill", "doors start at the floor; 'sill' is for windows")
            sill = 0.0
            head = height + (au.DOOR_HEAD if kind in au.HINGED_DOORS else 0.0)

        at = _point(raw["at"], f"{here}.at") if "at" in raw else None
        wall = raw.get("wall")
        offset = _length(raw, "offset", here) if "offset" in raw else None
        if (at is None) == (wall is None):
            raise SpecError(here, "place an opening with either 'at: [x, y]' or 'wall' + 'offset'")
        if wall is not None:
            if wall not in wall_ids:
                raise SpecError(f"{here}.wall", f"unknown wall id '{wall}'")
            if offset is None:
                raise SpecError(here, "'wall' needs 'offset': from the wall's first point to the opening centre")
        into = raw.get("into")
        hinge = _choice(raw, "hinge", ("left", "right"), here, "left")
        openings.append(Opening(kind, width, height, sill, head, at, wall, offset, into, hinge, here))
    return openings


def _default_floor(room_name: str) -> str:
    lowered = room_name.lower()
    for keywords, finish in au.ROOM_FLOORS:
        if any(k in lowered for k in keywords):
            return finish
    return au.DEFAULT_FLOOR


def _rooms(data, finishes: dict[str, Finish], where: str) -> list[Room]:
    rooms, names = [], set()
    for i, raw in enumerate(_list(data, where)):
        here = f"{where}[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, {"name", "at", "floor", "walls", "ceiling", "label_at"}, here)
        name = raw.get("name")
        if not name:
            raise SpecError(f"{here}.name", "required")
        if name in names:
            raise SpecError(f"{here}.name", f"duplicate room name '{name}' in this storey")
        names.add(name)
        floor = raw.get("floor", _default_floor(name))
        wet = _default_floor(name) == "tiles_light"
        walls = raw.get("walls", "tiles_wet_wall" if wet else "paint_white")
        ceiling = raw.get("ceiling", "ceiling_white")
        for key, value in (("floor", floor), ("walls", walls), ("ceiling", ceiling)):
            if value not in finishes:
                raise SpecError(f"{here}.{key}", f"unknown finish '{value}'")
        at = _point(raw.get("at"), f"{here}.at")
        label_at = _point(raw["label_at"], f"{here}.label_at") if "label_at" in raw else None
        rooms.append(Room(str(name), at, floor, walls, ceiling, label_at, here))
    return rooms


_STAIR_KEYS = {"type", "start", "direction", "width", "going", "turn", "landing_at", "gap", "finish"}


def _stairs(data, finishes: dict[str, Finish], where: str) -> list[Stair]:
    stairs = []
    for i, raw in enumerate(_list(data, where)):
        here = f"{where}[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, _STAIR_KEYS, here)
        kind = _choice(raw, "type", ("straight", "l_shaped", "u_shaped"), here, "straight")
        direction = raw.get("direction")
        if isinstance(direction, str) and direction.lower() in COMPASS:
            bearing = COMPASS[direction.lower()]
        elif isinstance(direction, int | float) and not isinstance(direction, bool):
            bearing = float(direction) % 360
        else:
            raise SpecError(f"{here}.direction", "use north, east, south, west, or a compass bearing in degrees")
        landing_at = raw.get("landing_at")
        if landing_at is not None and (not isinstance(landing_at, int) or landing_at < 2):
            raise SpecError(f"{here}.landing_at", "a whole number of risers, at least 2")
        finish = raw.get("finish", "stair_timber")
        if finish not in finishes:
            raise SpecError(f"{here}.finish", f"unknown finish '{finish}'")
        stairs.append(
            Stair(
                kind=kind,
                start=_point(raw.get("start"), f"{here}.start"),
                bearing=bearing,
                width=_length(raw, "width", here, 1000),
                going=_length(raw, "going", here, 250),
                turn=_choice(raw, "turn", ("left", "right"), here, "left"),
                landing_at=landing_at,
                gap=_length(raw, "gap", here, 100),
                finish=finish,
                where=here,
            )
        )
    return stairs


_ROOF_KEYS = {"type", "over", "outline", "pitch", "eaves", "fascia", "ridge", "down", "parapet", "finish"}
ROOF_DEFAULTS = {
    "hip": {"pitch": 22.5, "eaves": 450},
    "gable": {"pitch": 22.5, "eaves": 450},
    "skillion": {"pitch": 5, "eaves": 450},
    "flat": {"pitch": 0, "eaves": 0},
}


def _roofs(data, finishes: dict[str, Finish], storey_names: list[str], where: str) -> list[Roof]:
    roofs = []
    for i, raw in enumerate(_list(data, where)):
        here = f"{where}[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, _ROOF_KEYS, here)
        kind = _choice(raw, "type", tuple(ROOF_DEFAULTS), here, "hip")
        defaults = ROOF_DEFAULTS[kind]
        over = raw.get("over", storey_names[-1])
        if over not in storey_names:
            raise SpecError(f"{here}.over", f"unknown storey '{over}'; storeys: {storey_names}")
        pitch = float(raw.get("pitch", defaults["pitch"]))
        if kind != "flat" and not 1 <= pitch <= 60:
            raise SpecError(f"{here}.pitch", "degrees between 1 and 60")
        ridge = raw.get("ridge")
        ridge_ok = ridge in (None, "east-west", "north-south") or (
            isinstance(ridge, int | float) and not isinstance(ridge, bool)
        )
        if kind == "gable" and not ridge_ok:
            raise SpecError(f"{here}.ridge", "east-west, north-south, or the ridge's compass bearing in degrees")
        if isinstance(ridge, int | float) and not isinstance(ridge, bool):
            ridge = float(ridge) % 360
        down = raw.get("down")
        if kind == "skillion":
            if not isinstance(down, str) or down.lower() not in COMPASS:
                raise SpecError(f"{here}.down", "a skillion needs its low side: north, east, south or west")
            down = down.lower()
        finish = raw.get("finish", "roof_dark")
        if finish not in finishes:
            raise SpecError(f"{here}.finish", f"unknown finish '{finish}'")
        outline = _wall_points(raw["outline"], f"{here}.outline", True) if "outline" in raw else None
        eaves = _length(raw, "eaves", here, defaults["eaves"])
        if eaves < 0:
            raise SpecError(f"{here}.eaves", "the overhang past the walls; 0 or more")
        fascia = _length(raw, "fascia", here, 300 if kind == "flat" else 250)
        if fascia <= 0:
            raise SpecError(f"{here}.fascia", "must be positive")
        roofs.append(
            Roof(
                kind=kind,
                over=over,
                outline=outline,
                pitch=pitch,
                eaves=eaves,
                fascia=fascia,
                ridge=ridge,
                down=down,
                parapet=_length(raw, "parapet", here, 0),
                finish=finish,
                where=here,
            )
        )
    return roofs


_STOREY_KEYS = {
    "name", "level", "height", "floor", "walls", "openings", "rooms",
    "separators", "slab_extensions", "items", "stairs",
}  # fmt: skip


SHEETS = ("A4", "A3", "A2", "A1")
SCALES = (50, 100, 200, 250, 500)


def _settings(data) -> dict:
    raw = _mapping(data, "settings")
    _unknown_keys(raw, set(au.PLAN), "settings")
    settings = {**au.PLAN, **raw}
    scale = settings["scale"]
    if isinstance(scale, bool) or scale not in SCALES:
        raise SpecError("settings.scale", f"one of {list(SCALES)} (1:100 is usual)")
    if settings["sheet"] not in SHEETS:
        raise SpecError("settings.sheet", f"one of {list(SHEETS)}")
    cut = _length(settings, "cut_height", "settings")
    if not 300 <= cut <= 2400:
        raise SpecError("settings.cut_height", "the plan section height above the floor, 300 to 2400 (1200 is usual)")
    return {**settings, "cut_height": cut}


def load_plan(path: str | Path) -> Plan:
    path = Path(path)
    if path.is_dir():
        path = path / "plan.yaml"
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise SpecError(str(path), f"invalid YAML: {exc}") from None
    plan = parse_plan(data)
    plan.source = path
    return plan


def parse_plan(data) -> Plan:
    data = _mapping(data, "plan")
    _unknown_keys(data, {"project", "settings", "finishes", "wall_types", "storeys", "roof"}, "plan")
    project = _mapping(data.get("project"), "project")
    _unknown_keys(project, {"name", "address", "client", "north"}, "project")
    name = str(project.get("name") or "Untitled")
    north = project.get("north", 0)
    if isinstance(north, bool) or not isinstance(north, int | float):
        raise SpecError("project.north", "degrees clockwise from plan-up to true north")
    project = {**project, "north": float(north) % 360}
    settings = _settings(data.get("settings"))
    finishes = _finishes(data.get("finishes"), "finishes")
    wall_types = _wall_types(data.get("wall_types"), finishes, "wall_types")

    storeys: list[Storey] = []
    wall_ids: set[str] = set()
    raw_storeys = _list(data.get("storeys"), "storeys")
    if not raw_storeys:
        raise SpecError("storeys", "at least one storey is required")
    for i, raw in enumerate(raw_storeys):
        here = f"storeys[{i}]"
        raw = _mapping(raw, here)
        _unknown_keys(raw, _STOREY_KEYS, here)
        storey_name = str(raw.get("name") or f"Level {i + 1}")
        if storey_name in {s.name for s in storeys}:
            raise SpecError(f"{here}.name", f"there is already a storey called '{storey_name}'")
        height = _length(raw, "height", here, au.STOREY["height"])
        if not 1800 <= height <= 6000:
            raise SpecError(f"{here}.height", f"{height:.0f} is not a room height (floor to ceiling in mm)")
        floor = _length(raw, "floor", here, au.STOREY["ground_floor" if i == 0 else "upper_floor"])
        if not 0 <= floor <= 1500:
            raise SpecError(f"{here}.floor", "the floor structure's thickness in mm, 0 to 1500")
        if "level" in raw:
            level = _length(raw, "level", here)
        elif i == 0:
            level = 0.0
        else:
            below = storeys[-1]
            level = below.level + below.height + floor
        if storeys and level < storeys[-1].level + storeys[-1].height + floor - 0.5:
            raise SpecError(f"{here}.level", "clashes with the storey below (level < below's ceiling + this floor)")

        walls = _walls(raw.get("walls"), wall_types, f"{here}.walls", wall_ids)
        storey_wall_ids = {w.id for w in walls}
        storeys.append(
            Storey(
                index=i,
                name=storey_name,
                level=level,
                height=height,
                floor=floor,
                walls=walls,
                openings=_openings(raw.get("openings"), storey_wall_ids, f"{here}.openings"),
                rooms=_rooms(raw.get("rooms"), finishes, f"{here}.rooms"),
                separators=[
                    _wall_points(s, f"{here}.separators[{j}]", False)
                    for j, s in enumerate(_list(raw.get("separators"), f"{here}.separators"))
                ],
                slab_extensions=[
                    _wall_points(s, f"{here}.slab_extensions[{j}]", True)
                    for j, s in enumerate(_list(raw.get("slab_extensions"), f"{here}.slab_extensions"))
                ],
                items=_list(raw.get("items"), f"{here}.items"),
                stairs=_stairs(raw.get("stairs"), finishes, f"{here}.stairs"),
                where=here,
            )
        )
    roofs = _roofs(data.get("roof"), finishes, [s.name for s in storeys], "roof")
    return Plan(name, project, settings, finishes, wall_types, storeys, roofs)
