"""Stairs between a storey and the one above: treads and landings, the void
they need in the upper floor, the balustrade around that void, plan symbols.

A stair is modelled as a folded slab (a stepped top, a stepped soffit a
riser and a bit below it, open underneath), built with the band-stack kernel
so its faces conform like the rest of the model. Riser count comes from the
storey-to-storey rise; warnings flag Australian (NCC) limits that are not met.
"""

import math
from dataclasses import dataclass, field

import shapely
from shapely.geometry import LineString, Polygon

from . import au_defaults as au
from .geometry.solid import Face, Prism, build_solid, clean, polygons, union
from .geometry.storey import ResolvedStorey
from .spec import SpecError, Stair

BALUSTRADE_THICKNESS = 30.0
RAIL_DEPTH = 50.0  # dark top rail over the glass panels
SOFFIT = 40.0  # each step's slab reaches this far below the tread behind it
WALL_TOUCH = 150.0  # a void edge this close to a wall needs no balustrade (it's a ledge, not a drop)

Vec = tuple[float, float]


@dataclass
class Tread:
    polygon: Polygon
    top: float  # above the lower FFL
    nosing: LineString  # the edge you step up onto
    direction: Vec  # walking up


@dataclass
class ResolvedStair:
    stair: Stair
    lower: ResolvedStorey
    upper: ResolvedStorey
    risers: int
    riser: float
    treads: list[Tread]
    arrival: LineString  # the top riser, where the stair meets the upper floor
    void: Polygon
    balustrade: list[Polygon] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def footprint(self):
        return union(t.polygon for t in self.treads)


def _point(origin: Vec, u_dir: Vec, v_dir: Vec, u: float, v: float) -> Vec:
    return (origin[0] + u_dir[0] * u + v_dir[0] * v, origin[1] + u_dir[1] * u + v_dir[1] * v)


def _tread(origin, u_dir, v_dir, u0, u1, v0, v1, top) -> Tread:
    corners = [_point(origin, u_dir, v_dir, u, v) for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    nosing = LineString([corners[0], corners[3]])
    return Tread(Polygon(corners), top, nosing, u_dir if u1 >= u0 else (-u_dir[0], -u_dir[1]))


def _risers(rise: float) -> tuple[int, float]:
    count = max(2, round(rise / au.STAIR["riser_target"]))
    while rise / count > au.STAIR["riser_max"]:
        count += 1
    return count, rise / count


def _layout(stair: Stair, risers: int, riser: float) -> tuple[list[Tread], LineString, list[int]]:
    """Treads, the arrival line, and risers per flight."""
    g, w = stair.going, stair.width
    bearing = math.radians(stair.bearing)
    d = (math.sin(bearing), math.cos(bearing))  # compass: 0 = north (+y), 90 = east (+x)
    left = (-d[1], d[0])
    start = stair.start

    if stair.kind == "straight":
        treads = [_tread(start, d, left, (k - 1) * g, k * g, -w / 2, w / 2, k * riser) for k in range(1, risers)]
        end = (risers - 1) * g
        return treads, LineString([_point(start, d, left, end, -w / 2), _point(start, d, left, end, w / 2)]), [risers]

    n1 = stair.landing_at or risers // 2
    if not 2 <= n1 <= risers - 2:
        raise SpecError(f"{stair.where}.landing_at", f"leave 2+ of the {risers} risers each side of the landing")
    turn = 1.0 if stair.turn == "left" else -1.0
    treads = [_tread(start, d, left, (k - 1) * g, k * g, -w / 2, w / 2, k * riser) for k in range(1, n1)]
    landing_u = (n1 - 1) * g
    flights = [n1, risers - n1]

    if stair.kind == "l_shaped":
        treads.append(_tread(start, d, left, landing_u, landing_u + w, -w / 2, w / 2, n1 * riser))
        origin = _point(start, d, left, landing_u + w / 2, turn * w / 2)
        d2 = (turn * left[0], turn * left[1])
        left2 = (-d2[1], d2[0])
        for j, k in enumerate(range(n1 + 1, risers)):
            treads.append(_tread(origin, d2, left2, j * g, (j + 1) * g, -w / 2, w / 2, k * riser))
        end = (risers - n1 - 1) * g
        arrival = LineString([_point(origin, d2, left2, end, -w / 2), _point(origin, d2, left2, end, w / 2)])
        return treads, arrival, flights

    # u_shaped: a half landing across both flights, the second flight running back alongside.
    offset = turn * (w + stair.gap)
    v_lo, v_hi = sorted((-turn * w / 2, offset + turn * w / 2))
    treads.append(_tread(start, d, left, landing_u, landing_u + w, v_lo, v_hi, n1 * riser))
    for j, k in enumerate(range(n1 + 1, risers)):
        u_hi, u_lo = landing_u - j * g, landing_u - (j + 1) * g
        treads.append(_tread(start, d, left, u_hi, u_lo, offset - w / 2, offset + w / 2, k * riser))
    end = landing_u - (risers - n1 - 1) * g
    arrival = LineString([_point(start, d, left, end, offset - w / 2), _point(start, d, left, end, offset + w / 2)])
    return treads, arrival, flights


def resolve_stair(stair: Stair, lower: ResolvedStorey, upper: ResolvedStorey | None) -> ResolvedStair:
    if upper is None:
        raise SpecError(stair.where, "a stair needs a storey above it to reach")
    rise = upper.storey.level - lower.storey.level
    risers, riser = _risers(rise)
    treads, arrival, flights = _layout(stair, risers, riser)
    warnings = []

    limits = au.STAIR
    going = stair.going
    two_r_g = 2 * riser + going
    if not limits["going_min"] <= going <= limits["going_max"]:
        warnings.append(f"{stair.where}: going {going:.0f} is outside {limits['going_min']}-{limits['going_max']}")
    if not limits["two_r_plus_g"][0] <= two_r_g <= limits["two_r_plus_g"][1]:
        warnings.append(f"{stair.where}: 2R+G = {two_r_g:.0f} is outside {limits['two_r_plus_g']}")
    if max(flights) > limits["max_risers_per_flight"]:
        warnings.append(f"{stair.where}: a flight has {max(flights)} risers (max {limits['max_risers_per_flight']}); "
                        "use l_shaped or u_shaped with a landing")  # fmt: skip

    underside = rise - upper.storey.floor
    void = clean(union(t.polygon for t in treads if t.top > underside - limits["headroom"]))
    footprint = union(t.polygon for t in treads)
    if footprint.intersection(lower.walls).area > 10_000:
        warnings.append(f"{stair.where}: the stair runs into a wall on {lower.storey.name}")
    if not lower.shell.buffer(1).covers(footprint):
        warnings.append(f"{stair.where}: the stair extends outside {lower.storey.name}")
    if void.intersection(upper.walls).area > 10_000:
        warnings.append(f"{stair.where}: its void cuts under a wall on {upper.storey.name}")

    resolved = ResolvedStair(stair, lower, upper, risers, riser, treads, arrival, void, warnings=warnings)
    resolved.balustrade = _balustrade(resolved)
    return resolved


def _balustrade(rs: ResolvedStair) -> list[Polygon]:
    """Strips along the void's edges, except where the stair arrives or a wall runs alongside.

    Each strip runs a thickness past both ends of its edge, so strips meeting
    at a corner overlap into one L instead of touching at a point."""
    strips = []
    t = BALUSTRADE_THICKNESS
    for poly in polygons(shapely.simplify(rs.void, 0.5)):  # merge the collinear tread edges
        ring = list(shapely.orient_polygons(poly).exterior.coords)  # counter-clockwise: outside is right
        for a, b in zip(ring, ring[1:], strict=False):
            edge = LineString([a, b])
            if edge.length < 1 or edge.buffer(1).covers(rs.arrival) or rs.arrival.buffer(1).covers(edge):
                continue
            if edge.distance(rs.upper.walls) < WALL_TOUCH:
                continue
            ux, uy = (b[0] - a[0]) / edge.length, (b[1] - a[1]) / edge.length
            nx, ny = uy, -ux
            a2, b2 = (a[0] - ux * t, a[1] - uy * t), (b[0] + ux * t, b[1] + uy * t)
            strips.append(Polygon([a2, b2, (b2[0] + nx * t, b2[1] + ny * t), (a2[0] + nx * t, a2[1] + ny * t)]))
    return strips


def resolve_stairs(storeys: list[ResolvedStorey]) -> list[ResolvedStair]:
    stairs = []
    for i, lower in enumerate(storeys):
        upper = storeys[i + 1] if i + 1 < len(storeys) else None
        for stair in lower.storey.stairs:
            resolved = resolve_stair(stair, lower, upper)
            upper.voids.append(resolved.void)
            for room in upper.rooms:
                room.void_area += room.polygon.intersection(resolved.void).area
            lower.warnings.extend(resolved.warnings)
            stairs.append(resolved)
    return stairs


def stair_faces(rs: ResolvedStair) -> list[Face]:
    """A folded slab: each tread is a step one riser plus SOFFIT deep, so the
    steps overlap into one zigzag with a stepped underside, and the space
    under the stair is open."""
    ffl, finish = rs.lower.storey.level, rs.stair.finish
    depth = rs.riser + SOFFIT
    prisms = [Prism(t.polygon, max(ffl, ffl + t.top - depth), ffl + t.top) for t in rs.treads]
    return build_solid(prisms, [], lambda *_: finish, lambda *_: finish)


def balustrade_faces(stairs: list[ResolvedStair]) -> list[Face]:
    """Glass panels with a dark top rail around the voids stairs arrive through."""
    strips = [s for rs in stairs for s in rs.balustrade]
    if not strips:
        return []
    ffl = stairs[0].upper.storey.level
    top = ffl + au.STAIR["balustrade_height"]
    rail = top - RAIL_DEPTH
    solid = [Prism(union(strips), ffl, rail), Prism(union(strips), rail, top)]

    def horizontal(_point, z, _facing_up):
        return "balustrade" if z >= rail - 0.5 else "glass"

    return build_solid(solid, [], horizontal, lambda _mid, _normal, z: "balustrade" if z > rail else "glass")
