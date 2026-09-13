"""Roofs over a storey: hip, gable, skillion and flat.

A roof is built from convex parts. A pitched part is a set of planes rising
from its eaves at the pitch (all sides for a hip, the long sides for a gable,
the lowest side for a skillion), and its surface is the lowest plane at each
point. Parts over the same storey combine by taking the highest surface, so
two overlapping hipped rectangles make an L-shaped roof with correct valleys.
A non-convex outline is split into such parts automatically (see _outlines).

The surface is found on a planar arrangement: every plane-plane intersection
line, clipped to where both planes apply, is noded together with the part
outlines into one snap-rounded subdivision, and each cell is assigned the
part and plane that win at its interior. Faces are then built cell by cell:

- the top of each cell, lifted onto its plane;
- where neighbouring cells disagree about a shared edge's height (a lower
  part meeting a higher one), a vertical step face closing the gap;
- around the footprint, a fascia band down to the storey's ceiling and, where
  the surface rises above the eaves at the edge (gable ends, a skillion's
  high side), a vertical face in the wall's cladding;
- the underside at ceiling height.

Every face uses the arrangement's shared vertices, so the solid is closed.
"""

import math
from dataclasses import dataclass
from functools import cached_property

import shapely
import shapely.affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.prepared import prep

from .geometry.solid import Arrangement, Face, Prism, build_solid, clean, horizontal_faces, polygons, triangulate, union
from .geometry.storey import ResolvedStorey
from .spec import COMPASS, Roof, SpecError

RIDGE_TOLERANCE = math.cos(math.radians(10))  # edges within 10 degrees of the ridge carry eaves
DOWN_TOLERANCE = math.cos(math.radians(45))  # skillion: edges facing within 45 degrees of `down`
PARAPET_THICKNESS = 150.0
HEIGHT_SNAP = 0.5  # mm; heights this close to the eaves, or to each other at a vertex, are the same
JOG = 5.0  # mm; kinks in an outline smaller than this are ignored

Point2 = tuple[float, float]


@dataclass(frozen=True)
class Plane:
    """z = a·x + b·y + c"""

    a: float
    b: float
    c: float

    def z(self, x: float, y: float) -> float:
        return self.a * x + self.b * y + self.c


@dataclass
class RoofPart:
    roof: Roof
    polygon: Polygon  # eaves outline
    planes: list[Plane]  # empty: flat at eaves height

    def surface(self, x: float, y: float, eaves_z: float) -> tuple[float, int]:
        if not self.planes:
            return eaves_z, -1
        heights = [p.z(x, y) for p in self.planes]
        best = min(range(len(heights)), key=heights.__getitem__)
        return heights[best], best


@dataclass
class RoofCell:
    polygon: Polygon  # oriented: exterior counter-clockwise
    part: int
    plane: Plane | None  # None: flat at eaves height


@dataclass
class RoofPiece:
    """One plane's region of the roof, for the roof plan."""

    polygon: Polygon
    plane: Plane | None
    part: int


@dataclass
class ResolvedRoof:
    storey: ResolvedStorey
    parts: list[RoofPart]
    base: float  # underside: the storey's ceiling
    eaves_z: float  # top of the fascia, where the planes start
    footprint: Polygon
    arrangement: Arrangement
    cells: dict[int, RoofCell]  # by arrangement cell index; only cells inside the footprint
    finish: str

    def height(self, x: float, y: float) -> float:
        """The roof surface: the highest of the parts covering a point."""
        best = None
        point = Point(x, y)
        for part, prepared in zip(self.parts, self._prepared, strict=True):
            if prepared.covers(point):
                h = part.surface(x, y, self.eaves_z)[0]
                best = h if best is None else max(best, h)
        if best is None or abs(best - self.eaves_z) < HEIGHT_SNAP:
            return self.eaves_z
        return round(best, 2)

    def __post_init__(self):
        self._prepared = [prep(part.polygon.buffer(0.5)) for part in self.parts]

    @cached_property
    def pieces(self) -> list[RoofPiece]:
        groups: dict[tuple[int, int], list[Polygon]] = {}
        for cell in self.cells.values():
            groups.setdefault((cell.part, id(cell.plane)), []).append(cell.polygon)
        pieces = []
        for (part, _), cells in groups.items():
            plane = next(c.plane for c in self.cells.values() if c.part == part and id(c.plane) == _)
            pieces.extend(RoofPiece(poly, plane, part) for poly in polygons(union(cells)))
        return pieces

    def finish_of(self, cell: RoofCell) -> str:
        return self.parts[cell.part].roof.finish


def _convex(poly: Polygon) -> bool:
    return poly.convex_hull.area - poly.area < 1.0


def _rectilinear(poly: Polygon) -> bool:
    coords = list(poly.exterior.coords)
    return all(abs(x0 - x1) < 0.5 or abs(y0 - y1) < 0.5 for (x0, y0), (x1, y1) in zip(coords, coords[1:], strict=False))


def _grain(poly: Polygon) -> float:
    """The bearing of the longest edge, degrees counter-clockwise from +x."""
    ring = list(poly.exterior.coords)
    (x0, y0), (x1, y1) = max(zip(ring, ring[1:], strict=False), key=lambda e: math.dist(*e))
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def _wings(poly: Polygon) -> list[Polygon] | None:
    """The maximal rectangles of a rectilinear outline at any orientation (an
    L at 30 degrees is still an L), or None if the outline isn't rectilinear."""
    angle = _grain(poly)
    squared = shapely.affinity.rotate(poly, -angle, origin=(0, 0))
    if not _rectilinear(shapely.simplify(squared, JOG)):
        return None
    rects = _maximal_rectangles(shapely.simplify(squared, JOG))
    return [shapely.affinity.rotate(r, angle, origin=(0, 0)) for r in rects]


def _maximal_rectangles(poly: Polygon) -> list[Polygon]:
    """Every axis-aligned rectangle inside a rectilinear polygon that no larger
    inside rectangle contains: the wings of an L, T or U, overlapping."""
    xs = sorted({round(x, 1) for x, _ in poly.exterior.coords})
    ys = sorted({round(y, 1) for _, y in poly.exterior.coords})
    room = prep(poly.buffer(0.5))
    rects = [
        shapely.box(x0, y0, x1, y1)
        for i, x0 in enumerate(xs)
        for x1 in xs[i + 1:]
        for k, y0 in enumerate(ys)
        for y1 in ys[k + 1:]
        if room.covers(shapely.box(x0, y0, x1, y1))
    ]
    return [r for r in rects if not any(o.area > r.area and o.buffer(0.5).covers(r) for o in rects)]


def _convex_partition(poly: Polygon) -> list[Polygon]:
    """Convex pieces of a polygon: its triangles, merged while the union stays convex."""
    pieces = list(shapely.get_parts(shapely.constrained_delaunay_triangles(poly)))
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(pieces):
            for j in range(i + 1, len(pieces)):
                b = pieces[j]
                if a.intersection(b).length < 1:
                    continue  # not neighbours along an edge
                joined = shapely.simplify(a.union(b), 0.5)
                if joined.geom_type == "Polygon" and _convex(joined):
                    pieces[i] = joined
                    del pieces[j]
                    merged = True
                    break
            if merged:
                break
    return pieces


def _outlines(roof: Roof, rs: ResolvedStorey) -> list[Polygon]:
    """The convex parts a roof is built from. A convex outline is one part; a
    rectilinear one (L, T, U) is its maximal rectangles, which overlap so the
    hips of one wing run into the other as valleys; anything else is a convex
    partition, one hip end per piece. Skillion and flat roofs need no parts."""
    if roof.outline is not None:
        outline = Polygon(roof.outline)
    else:
        parts = polygons(rs.shell)
        if len(parts) != 1:
            raise SpecError(roof.where, f"{rs.storey.name} is not one outline; give the roof an 'outline'")
        outline = parts[0]
    outline = shapely.simplify(outline, JOG)  # merge collinear points and tiny jogs: they would duplicate planes
    if not outline.is_valid:
        raise SpecError(roof.where, "the roof outline crosses itself")
    if roof.kind in ("flat", "skillion") or _convex(outline):
        return [outline]
    wings = _wings(outline)
    if wings:
        return wings
    pieces = _convex_partition(outline)
    rs.warnings.append(
        f"{roof.where}: the outline isn't rectilinear, so the {roof.kind} roof is {len(pieces)} convex pieces "
        "with a hip end each; give the roof one 'outline' per wing for a cleaner result"
    )
    return pieces


def _planes(roof: Roof, eaves: Polygon, eaves_z: float) -> list[Plane]:
    if roof.kind == "flat":
        return []
    slope = math.tan(math.radians(roof.pitch))
    ring = list(shapely.orient_polygons(eaves).exterior.coords)[:-1]
    if roof.kind == "gable":
        if roof.ridge == "east-west":
            ridge_dir = (1.0, 0.0)
        elif roof.ridge == "north-south":
            ridge_dir = (0.0, 1.0)
        elif isinstance(roof.ridge, int | float):  # a compass bearing
            ridge_dir = (math.sin(math.radians(roof.ridge)), math.cos(math.radians(roof.ridge)))
        else:  # along the longest side, whichever way the building faces
            (x0, y0), (x1, y1) = max(zip(ring, ring[1:] + ring[:1], strict=True), key=lambda e: math.dist(*e))
            length = math.dist((x0, y0), (x1, y1))
            ridge_dir = ((x1 - x0) / length, (y1 - y0) / length)
    if roof.kind == "skillion":
        bearing = math.radians(COMPASS[roof.down])
        down = (math.sin(bearing), math.cos(bearing))

    planes = []
    lowest = None  # skillion: (how far down-slope its eave line is, plane)
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux  # inward: the ring is counter-clockwise
        if roof.kind == "gable" and abs(ux * ridge_dir[0] + uy * ridge_dir[1]) < RIDGE_TOLERANCE:
            continue  # a gable end
        # Rises inward from the eave line at eaves height.
        plane = Plane(slope * nx, slope * ny, eaves_z - slope * (nx * x0 + ny * y0))
        if roof.kind == "skillion":
            if (-nx * down[0] - ny * down[1]) < DOWN_TOLERANCE:
                continue  # faces the wrong way
            reach = ((x0 + x1) / 2) * down[0] + ((y0 + y1) / 2) * down[1]
            if lowest is None or reach > lowest[0]:
                lowest = (reach, plane)  # the eave furthest down-slope; one plane covers any outline
            continue
        planes.append(plane)
    if lowest is not None:
        planes.append(lowest[1])
    if roof.kind == "gable" and len(planes) < 2:
        raise SpecError(roof.where, "a gable needs two sides parallel to its ridge; use 'hip' for this shape")
    if not planes:
        raise SpecError(roof.where, "no eave faces that way; check 'down' or 'ridge'")
    return planes


def _intersection_line(p: Plane, q: Plane, region: Polygon) -> LineString | None:
    """Where two planes meet, across `region` and a little past its edge so
    the line nodes onto the outline instead of dangling a hair short of it."""
    a, b, c = p.a - q.a, p.b - q.b, p.c - q.c
    norm = math.hypot(a, b)
    if norm < 1e-9:
        return None  # parallel planes never cross
    minx, miny, maxx, maxy = region.bounds
    reach = 2 * math.hypot(maxx - minx, maxy - miny) + 1
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    # Closest point on the line a·x + b·y + c = 0 to the region's centre, then run along it.
    t = (a * cx + b * cy + c) / (norm * norm)
    px, py = cx - a * t, cy - b * t
    dx, dy = -b / norm, a / norm
    line = LineString([(px - dx * reach, py - dy * reach), (px + dx * reach, py + dy * reach)])
    clipped = line.intersection(region.buffer(1.0))
    return None if clipped.is_empty else clipped


def check_cover(storeys: list[ResolvedStorey], roofs: list[ResolvedRoof]) -> None:
    """Warn where a storey has neither a storey above nor a roof: open to the sky."""
    for i, rs in enumerate(storeys):
        above = union(s.slab for s in storeys[i + 1:])
        covered = union([above, *(r.footprint for r in roofs if r.storey is rs)])
        open_sky = clean(rs.shell.difference(covered))
        if open_sky.area > 1e6:
            rs.warnings.append(f"{rs.storey.name}: {open_sky.area / 1e6:.1f} m² has no roof or storey above it")


def resolve_roofs(roofs: list[Roof], storeys: list[ResolvedStorey]) -> list[ResolvedRoof]:
    by_storey: dict[str, list[Roof]] = {}
    for roof in roofs:
        by_storey.setdefault(roof.over, []).append(roof)
    resolved = []
    for name, group in by_storey.items():
        rs = next(s for s in storeys if s.storey.name == name)
        base = rs.storey.level + rs.storey.height
        fascia = max(r.fascia for r in group)
        eaves_z = base + fascia
        parts = []
        for roof in group:
            for outline in _outlines(roof, rs):
                # Kept unrounded: the arrangement rounds all the roof's linework together.
                eaves = outline.buffer(roof.eaves, join_style="mitre")
                parts.append(RoofPart(roof, eaves, _planes(roof, eaves, eaves_z)))
        footprint = shapely.union_all([p.polygon for p in parts])
        # A lower roof stops where it meets a higher storey (a porch roof
        # against a two-storey wall); its planes carry on unchanged up to there.
        higher = shapely.union_all([s.slab for s in storeys if s.storey.level > base])
        if not higher.is_empty:
            footprint = footprint.difference(higher)
            if footprint.area < 1.0:
                raise SpecError(group[0].where, f"the roof over {name} is entirely under the storey above")
        arrangement, cells = _cells(parts, footprint, eaves_z)
        resolved.append(ResolvedRoof(rs, parts, base, eaves_z, footprint, arrangement, cells, group[0].finish))
    check_cover(storeys, resolved)
    return resolved


def _cells(parts: list[RoofPart], footprint: Polygon, eaves_z: float) -> tuple[Arrangement, dict[int, RoofCell]]:
    lines = [footprint.boundary] + [part.polygon.boundary for part in parts]
    for i, part in enumerate(parts):
        for j, p in enumerate(part.planes):
            for q in part.planes[j + 1:]:
                lines.append(_intersection_line(p, q, part.polygon))
        for other in parts[i + 1:]:
            overlap = part.polygon.intersection(other.polygon)
            if overlap.area < 1.0:
                continue
            flat = Plane(0.0, 0.0, eaves_z)
            for p in part.planes or [flat]:
                for q in other.planes or [flat]:
                    lines.append(_intersection_line(p, q, overlap))
    arrangement = Arrangement.of_lines(lines)
    covering = [prep(part.polygon.buffer(0.5)) for part in parts]

    cells: dict[int, RoofCell] = {}
    for index in arrangement.members(footprint):
        cell = arrangement.cells[index]
        inside = cell.representative_point()
        candidates = [i for i, prepared in enumerate(covering) if prepared.covers(inside)]
        if not candidates:  # a sliver the rounding left between parts: give it the nearest
            candidates = [min(range(len(parts)), key=lambda i: parts[i].polygon.distance(inside))]
        best = None
        for i in candidates:
            h, plane_index = parts[i].surface(inside.x, inside.y, eaves_z)
            if best is None or h > best[0] + 1e-6:
                best = (h, i, plane_index)
        _, part_index, plane_index = best
        plane = parts[part_index].planes[plane_index] if plane_index >= 0 else None
        cells[index] = RoofCell(cell, part_index, plane)
    return arrangement, cells


def _key3(p) -> Point2:
    return (round(p[0], 3), round(p[1], 3))


def _fan(points: list[tuple[float, float, float]], finish: str) -> list[Face]:
    """Triangles of a polygon given in order, ignoring repeated points."""
    pts: list[tuple[float, float, float]] = []
    for p in points:
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return [Face((pts[0], pts[i], pts[i + 1]), finish) for i in range(1, len(pts) - 1)]


def roof_faces(rr: ResolvedRoof) -> list[Face]:
    if all(not part.planes for part in rr.parts):
        return _flat_faces(rr)
    arrangement, cells, eaves = rr.arrangement, rr.cells, rr.eaves_z

    def raw_height(cell: RoofCell, v: Point2) -> float:
        h = cell.plane.z(*v) if cell.plane else eaves
        return eaves if abs(h - eaves) < HEIGHT_SNAP else round(h, 2)

    # One height per vertex per group of cells that agree on it (within
    # HEIGHT_SNAP), so faces meeting at a vertex share it exactly.
    per_vertex: dict[Point2, list[tuple[int, float]]] = {}
    for index, cell in cells.items():
        for a, _ in Arrangement.edges(cell.polygon):
            per_vertex.setdefault(a, []).append((index, raw_height(cell, a)))
    height: dict[tuple[int, Point2], float] = {}
    for v, entries in per_vertex.items():
        entries.sort(key=lambda e: e[1])
        cluster: list[tuple[int, float]] = []
        for entry in [*entries, None]:
            if entry is not None and (not cluster or entry[1] - cluster[0][1] <= HEIGHT_SNAP):
                cluster.append(entry)
                continue
            value = round(sum(h for _, h in cluster) / len(cluster), 2)
            for index, _ in cluster:
                height[(index, v)] = value
            cluster = [entry] if entry is not None else []

    # Every height any face uses at a vertex, so a vertical edge there can be
    # split at each of them: faces meeting along it then share whole edges.
    levels_at: dict[Point2, list[float]] = {}
    for (_, v), h in height.items():
        levels_at.setdefault(v, []).append(h)
    levels_at = {v: sorted({eaves, *hs}) for v, hs in levels_at.items()}

    def wall(a: Point2, b: Point2, low_a: float, low_b: float, high_a: float, high_b: float, finish: str) -> list[Face]:
        """A vertical face from the low heights up to the high ones along a->b,
        wound so it faces right of a->b, with every intermediate level as a vertex."""
        up_b = [(*b, h) for h in levels_at[b] if low_b < h < high_b]
        down_a = [(*a, h) for h in levels_at[a] if low_a < h < high_a][::-1]
        ring = [(*a, low_a), (*b, low_b), *up_b, (*b, high_b), (*a, high_a), *down_a]
        return _fan(ring, finish)

    faces: list[Face] = []
    for index, cell in cells.items():
        finish = rr.finish_of(cell)
        for a, b, c in triangulate(cell.polygon):
            ka, kb, kc = (_key3(a), _key3(b), _key3(c))
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0:
                kb, kc = kc, kb  # counter-clockwise in plan faces up once lifted
            faces.append(Face(tuple((*k, height[(index, k)]) for k in (ka, kb, kc)), finish))
        faces.extend(horizontal_faces(cell.polygon, rr.base, False, "ceiling_white"))

        for a, b in Arrangement.edges(cell.polygon):
            ha, hb = height[(index, a)], height[(index, b)]
            other = arrangement.neighbour(a, b)
            if other is None or other not in cells:
                faces.append(Face(((*a, rr.base), (*b, rr.base), (*b, eaves), (*a, eaves)), "fascia"))
                if ha != eaves or hb != eaves:
                    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    faces.extend(wall(a, b, eaves, eaves, ha, hb, rr.storey.nearest_wall(mid).type.outside))
                continue
            if other < index:
                continue  # the pair is handled from the other cell
            oa, ob = height[(other, a)], height[(other, b)]
            if ha == oa and hb == ob:
                continue
            # A step: a vertical face on the higher cell's side, facing the lower one.
            if ha + hb >= oa + ob:
                faces.extend(wall(a, b, oa, ob, ha, hb, finish))
            else:
                faces.extend(wall(b, a, hb, ha, ob, oa, rr.finish_of(cells[other])))
    return faces


def _flat_faces(rr: ResolvedRoof) -> list[Face]:
    parapet = max(part.roof.parapet for part in rr.parts)
    prisms = [Prism(rr.footprint, rr.base, rr.eaves_z)]
    if parapet > 0:
        ring = clean(rr.footprint.difference(rr.footprint.buffer(-PARAPET_THICKNESS, join_style="mitre")))
        prisms.append(Prism(ring, rr.eaves_z, rr.eaves_z + parapet))

    def horizontal(_point, z, facing_up):
        if not facing_up:
            return "ceiling_white"
        return rr.finish if abs(z - rr.eaves_z) < 0.5 else "fascia"

    return build_solid(prisms, [], horizontal, lambda *_: "fascia")
