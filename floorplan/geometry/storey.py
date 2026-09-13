"""Per-storey plan geometry: wall bodies, openings placed in walls, rooms.

Coordinates: x east, y north, millimetres, in plan. A storey's heights are
absolute (FFL = storey.level).
"""

import math
from dataclasses import dataclass, field

import shapely
from shapely.geometry import LinearRing, LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from ..spec import Opening, Room, SpecError, Storey, Wall
from .solid import clean, polygons, union

OPENING_SNAP = 250.0  # how far an opening's `at` may sit off its wall's centreline
CUT_OVERSHOOT = 5.0  # opening cuts extend this far past both wall faces
SIDE_PROBE = 150.0  # distance past a wall face used to ask "which room is there?"
MITRE_MIN = 0.1  # 1 + cos(turn); corners sharper than about 26 degrees are refused

Point2 = tuple[float, float]


def signed_area(points: list[tuple[float, float]]) -> float:
    return 0.5 * sum(
        x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1], strict=True)
    )


def centre_offset(wall: Wall) -> float:
    """Offset of the wall body's centreline from its path, positive to the left."""
    half = wall.type.thickness / 2
    if wall.align == "centre":
        return 0.0
    if wall.align in ("inside", "outside"):
        ccw = signed_area(wall.points) > 0
        # The path traces one face; the body extends away from it. For a CCW
        # ring the interior is on the left.
        body_left = (wall.align == "outside") == ccw
        return half if body_left else -half
    return half if wall.align == "left" else -half


def mitred_offset(points: list[Point2], offset: float, closed: bool, where: str = "") -> list[Point2]:
    """The polyline moved `offset` to its left (right if negative), corners mitred.

    Written out rather than using shapely.offset_curve, which returns a
    truncated open line when a ring is offset outwards."""
    n = len(points)
    if closed:
        prev = [points[i - 1] for i in range(n)]
        nxt = [points[(i + 1) % n] for i in range(n)]
    else:
        prev = [None, *points[:-1]]
        nxt = [*points[1:], None]
    out = []
    for p, v, q in zip(prev, points, nxt, strict=True):
        normals = []
        for a, b in ((p, v), (v, q)):
            if a is None or b is None:
                continue
            length = math.dist(a, b)
            normals.append((-(b[1] - a[1]) / length, (b[0] - a[0]) / length))
        if len(normals) == 1:
            (nx, ny) = normals[0]
            out.append((v[0] + nx * offset, v[1] + ny * offset))
            continue
        (n1x, n1y), (n2x, n2y) = normals
        denom = 1.0 + n1x * n2x + n1y * n2y  # (n1 + n2) . n1
        if denom < MITRE_MIN:
            raise SpecError(where, f"the corner at {[round(v[0]), round(v[1])]} is too sharp for a mitred wall")
        k = offset / denom
        out.append((v[0] + (n1x + n2x) * k, v[1] + (n1y + n2y) * k))
    return out


def wall_body(wall: Wall) -> BaseGeometry:
    """The wall's plan footprint: the centreline thickened, corners mitred."""
    half = wall.type.thickness / 2
    centre = wall_centreline(wall)
    if wall.closed:
        return clean(LinearRing(centre).buffer(half, join_style="mitre"))
    return clean(LineString(centre).buffer(half, cap_style="flat", join_style="mitre"))


def wall_centreline(wall: Wall) -> list[Point2]:
    """The wall body's centreline: the path moved sideways for its alignment."""
    offset = centre_offset(wall)
    centre = mitred_offset(wall.points, offset, wall.closed, wall.where) if offset else list(wall.points)
    line = LinearRing(centre) if wall.closed else LineString(centre)
    if not line.is_simple:  # an edge shorter than the mitres at its ends folded over
        raise SpecError(f"{wall.where}.points", "an edge is too short for the wall's thickness at its corners")
    return centre


@dataclass
class WallSegment:
    """One straight run of a wall, described by its body centreline."""

    wall: Wall
    index: int
    start: tuple[float, float]
    end: tuple[float, float]
    path_start: tuple[float, float] = (0.0, 0.0)  # the drawn point this run starts from
    path_length: float = 0.0  # length of the drawn edge (offsets are measured along it)

    @property
    def thickness(self) -> float:
        return self.wall.type.thickness

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def direction(self) -> tuple[float, float]:
        length = self.length
        return ((self.end[0] - self.start[0]) / length, (self.end[1] - self.start[1]) / length)

    @property
    def normal(self) -> tuple[float, float]:
        """Unit normal to the left of the segment's direction."""
        ux, uy = self.direction
        return (-uy, ux)

    def point(self, along: float, across: float = 0.0) -> tuple[float, float]:
        (ux, uy), (nx, ny) = self.direction, self.normal
        return (self.start[0] + ux * along + nx * across, self.start[1] + uy * along + ny * across)

    def project(self, p: tuple[float, float]) -> tuple[float, float]:
        """(distance along, signed distance across) of a point."""
        (ux, uy), (nx, ny) = self.direction, self.normal
        dx, dy = p[0] - self.start[0], p[1] - self.start[1]
        return (dx * ux + dy * uy, dx * nx + dy * ny)

    def rect(self, along0: float, along1: float, across0: float, across1: float) -> Polygon:
        return Polygon(
            [
                self.point(along0, across0),
                self.point(along1, across0),
                self.point(along1, across1),
                self.point(along0, across1),
            ]
        )


def wall_segments(wall: Wall) -> list[WallSegment]:
    """Straight runs of the body centreline, corner to mitred corner."""
    centre = wall_centreline(wall)
    points = centre + ([centre[0]] if wall.closed else [])
    drawn = wall.points + ([wall.points[0]] if wall.closed else [])
    return [
        WallSegment(wall, i, a, b, p, math.dist(p, q))
        for i, ((a, b), (p, q)) in enumerate(
            zip(zip(points, points[1:], strict=False), zip(drawn, drawn[1:], strict=False), strict=True)
        )
    ]


@dataclass
class PlacedOpening:
    opening: Opening
    segment: WallSegment
    along: float  # centre of the opening, measured along the segment
    cut: Polygon  # plan region removed from the wall
    side: int = 1  # +1 if the door opens to the segment's left (normal) side, -1 right

    @property
    def width(self) -> float:
        return self.opening.hole_width

    @property
    def centre(self) -> tuple[float, float]:
        return self.segment.point(self.along)

    def cut_by(self, cut_height: float) -> bool:
        """Does a plan section at this height above FFL pass through the opening?"""
        return self.opening.sill <= cut_height < self.opening.head


@dataclass
class ResolvedRoom:
    room: Room
    polygon: Polygon
    void_area: float = 0.0  # open to the storey below (stair voids); not floor area

    @property
    def area(self) -> float:
        return self.polygon.area - self.void_area

    @property
    def label_point(self) -> tuple[float, float]:
        if self.room.label_at:
            return self.room.label_at
        p = self.polygon.centroid
        if not self.polygon.contains(p):  # L-shaped rooms: centroid can fall outside
            p = self.polygon.representative_point()
        return (p.x, p.y)


@dataclass
class ResolvedStorey:
    storey: Storey
    bodies: list[tuple[Wall, BaseGeometry]]
    segments: list[WallSegment]
    walls: BaseGeometry  # union of wall bodies
    shell: BaseGeometry  # walls with enclosed areas filled in
    slab: BaseGeometry  # shell plus slab extensions
    openings: list[PlacedOpening]
    rooms: list[ResolvedRoom]
    unnamed: list[Polygon]
    warnings: list[str] = field(default_factory=list)
    voids: list[BaseGeometry] = field(default_factory=list)  # holes in this floor, e.g. for a stair below

    @property
    def ffl(self) -> float:
        return self.storey.level

    def room_at(self, p: tuple[float, float]) -> ResolvedRoom | None:
        point = Point(p)
        for room in self.rooms:
            if room.polygon.covers(point):
                return room
        return None

    def room_named(self, name: str) -> ResolvedRoom | None:
        return next((r for r in self.rooms if r.room.name == name), None)

    def nearest_wall(self, p: tuple[float, float]) -> Wall:
        point = Point(p)
        return min(self.bodies, key=lambda wb: wb[1].distance(point))[0]

    def plan_cut(self, cut_height: float) -> BaseGeometry:
        """Walls as cut by a plan section `cut_height` above FFL: bodies minus the
        openings that section passes through (high windows stay solid wall)."""
        return clean(self.walls.difference(union(o.cut for o in self.openings if o.cut_by(cut_height))))


def _place(op: Opening, segments: list[WallSegment]) -> tuple[WallSegment, float]:
    if op.at is not None:
        best = None
        for seg in segments:
            along, across = seg.project(op.at)
            if -seg.thickness <= along <= seg.length + seg.thickness:
                dist = abs(across)
                if dist <= seg.thickness / 2 + OPENING_SNAP and (best is None or dist < best[2]):
                    best = (seg, along, dist)
        if best is None:
            raise SpecError(f"{op.where}.at", f"no wall within {OPENING_SNAP:.0f} mm of {list(op.at)}")
        return best[0], best[1]

    # `offset` runs along the wall as drawn, from its first point. The body's
    # centreline starts and ends elsewhere (mitred corners, sideways
    # alignment), so translate onto the segment.
    remaining = op.offset
    wall_segs = [s for s in segments if s.wall.id == op.wall]
    for seg in wall_segs:
        if remaining <= seg.path_length + 0.5:
            return seg, seg.project(seg.path_start)[0] + remaining
        remaining -= seg.path_length
    total = sum(s.path_length for s in wall_segs)
    raise SpecError(f"{op.where}.offset", f"{op.offset:.0f} is past the end of wall '{op.wall}' ({total:.0f} long)")


def _regions(walls: BaseGeometry, shell: BaseGeometry, storey: Storey) -> list[Polygon]:
    """Enclosed areas between walls, split by separators and slab extensions."""
    lines: list[BaseGeometry] = [walls.boundary]
    for sep in storey.separators:
        line = LineString(sep)
        # Extend both ends slightly so a separator drawn to a wall face nodes onto it.
        (x0, y0), (x1, y1) = line.coords[0], line.coords[1]
        (xa, ya), (xb, yb) = line.coords[-2], line.coords[-1]
        d0, d1 = math.dist((x0, y0), (x1, y1)), math.dist((xa, ya), (xb, yb))
        coords = list(line.coords)
        coords[0] = (x0 - (x1 - x0) / d0 * 10, y0 - (y1 - y0) / d0 * 10)
        coords[-1] = (xb + (xb - xa) / d1 * 10, yb + (yb - ya) / d1 * 10)
        lines.append(LineString(coords))
    # Only the outdoor part of a slab extension's outline bounds a region; where
    # it overlaps the building it must not cut rooms in two.
    lines += [Polygon(ext).boundary.difference(shell.buffer(-1)) for ext in storey.slab_extensions]
    noded = shapely.union_all(lines)
    faces = shapely.polygonize(list(shapely.get_parts(noded)))
    regions = []
    for face in polygons(faces):
        face = clean(face)
        for part in polygons(face):
            if part.area > 10_000 and not walls.contains(part.representative_point()):
                regions.append(part)
    return regions


def resolve_storey(storey: Storey) -> ResolvedStorey:
    bodies = [(wall, wall_body(wall)) for wall in storey.walls]
    walls = union(body for _, body in bodies)
    if walls.is_empty:
        raise SpecError(f"{storey.where}.walls", "a storey needs at least one wall")
    shell = union(Polygon(p.exterior) for p in polygons(walls))
    slab = union([shell, *(Polygon(ext) for ext in storey.slab_extensions)])
    segments = [seg for wall in storey.walls for seg in wall_segments(wall)]
    warnings: list[str] = []

    openings = []
    for op in storey.openings:
        if op.head > storey.height + 0.5:
            raise SpecError(
                op.where, f"its head at {op.head:.0f} is above the {storey.height:.0f} ceiling of {storey.name}"
            )
        seg, along = _place(op, segments)
        half = op.hole_width / 2
        # At a corner the segment's centreline runs into the mitre with the
        # next segment; an opening has to stop at the inside face there.
        segments_of_wall = sum(1 for s in segments if s.wall is seg.wall)
        corner_at_start = seg.wall.closed or seg.index > 0
        corner_at_end = seg.wall.closed or seg.index < segments_of_wall - 1
        lo = seg.thickness / 2 if corner_at_start else 0.0
        hi = seg.length - (seg.thickness / 2 if corner_at_end else 0.0)
        if along - half < lo - 0.5 or along + half > hi + 0.5:
            clear = hi - lo
            raise SpecError(
                op.where,
                f"{op.hole_width:.0f} wide opening centred {along:.0f} along a run of wall '{seg.wall.id}' "
                f"with {clear:.0f} clear between its corners runs into a corner or past the end",
            )
        reach = seg.thickness / 2 + CUT_OVERSHOOT
        cut = seg.rect(along - half, along + half, -reach, reach)
        for other, body in bodies:
            if other is not seg.wall and cut.intersection(body).area > 2_000:
                warnings.append(f"{op.where}: overlaps wall '{other.id}'; is it too close to a junction?")
        for earlier in openings:
            if earlier.segment is seg and abs(earlier.along - along) < (earlier.width + op.hole_width) / 2:
                warnings.append(f"{op.where}: overlaps {earlier.opening.where} in wall '{seg.wall.id}'")
        openings.append(PlacedOpening(op, seg, along, cut))

    regions = _regions(walls, shell, storey)
    rooms, claimed = [], {}
    for room in storey.rooms:
        matches = [r for r in regions if r.covers(Point(room.at))]
        if not matches:
            raise SpecError(
                f"{room.where}.at",
                f"'{room.name}' at {list(room.at)} is not inside an enclosed area. "
                "Check its walls meet, or close an opening with a separator.",
            )
        if len(matches) > 1:
            raise SpecError(
                f"{room.where}.at",
                f"'{room.name}' at {list(room.at)} is on the line between two areas; move it into the room",
            )
        region = matches[0]
        key = region.wkb
        if key in claimed:
            raise SpecError(
                f"{room.where}.at",
                f"'{room.name}' is in the same area as '{claimed[key]}'; add a separator between them",
            )
        claimed[key] = room.name
        rooms.append(ResolvedRoom(room, region))
    unnamed = [r for r in regions if r.wkb not in claimed]

    resolved = ResolvedStorey(storey, bodies, segments, walls, shell, slab, openings, rooms, unnamed, warnings)
    for placed in openings:
        placed.side = _opening_side(resolved, placed)
    return resolved


def _opening_side(rs: ResolvedStorey, placed: PlacedOpening) -> int:
    """Which side of its wall a door opens into: +1 left of the segment, -1 right."""
    seg, op = placed.segment, placed.opening
    probe = seg.thickness / 2 + SIDE_PROBE
    left = rs.room_at(seg.point(placed.along, probe))
    right = rs.room_at(seg.point(placed.along, -probe))
    if op.into:
        if op.into == "outside":
            if left is None:
                return 1
            if right is None:
                return -1
        for side, room in ((1, left), (-1, right)):
            if room is not None and room.room.name == op.into:
                return side
        rs.warnings.append(f"{op.where}.into: '{op.into}' is not on either side of this opening")
    # External doors open inwards, even onto a porch that is itself a room.
    left_inside = rs.shell.covers(Point(seg.point(placed.along, probe)))
    right_inside = rs.shell.covers(Point(seg.point(placed.along, -probe)))
    if left_inside != right_inside:
        return 1 if left_inside else -1
    if left is None or right is None:
        return -1 if left is None else 1
    return 1 if left.area <= right.area else -1  # internal doors open into the smaller room
