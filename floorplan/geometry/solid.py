"""Band-stack solids: plan polygons extruded between heights, minus cuts,
emitted as a conforming set of planar faces.

The solid is sliced into horizontal bands at every height where anything
starts or stops (slab underside, floor, window sills and heads, ceiling).
Within a band the cross-section is constant.

SketchUp's DXF importer merges coplanar faces only across edges that match
exactly, so every face must share its edges exactly with its neighbours: no
corner of one face may sit in the middle of another's edge. To guarantee
that, every outline involved (prisms, cuts, and the polygons finishes are
split by) is noded into ONE snap-rounded planar arrangement, and every face
is built from that arrangement's cells:

- a band is a set of cells; its vertical faces are the cell edges along which
  the neighbouring cell is not in the band, extruded through the band;
- the horizontal faces at a band boundary are the cells that are in one band
  and not the other, triangulated on their own vertices.

Because bands and horizontal pieces are all made of the same cells, their
edges coincide by construction, for walls at any angle.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

GRID = 0.1  # mm; every arrangement is snap-rounded to this grid
DEGENERATE = 1e-6  # mm²; cells below this have no area to speak of
EMPTY = Polygon()

Point2 = tuple[float, float]
Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class Prism:
    """A plan region occupied (or, as a cut, vacated) between two heights."""

    polygon: BaseGeometry
    z0: float
    z1: float


@dataclass(frozen=True)
class Face:
    """A planar polygon, wound counter-clockwise when seen from its front."""

    points: tuple[Point3, ...]
    finish: str


# finish_horizontal(point inside the face, z, facing_up) -> finish
HorizontalFinish = Callable[[Point2, float, bool], str]
# finish_vertical(edge midpoint, outward normal, band mid z) -> finish
VerticalFinish = Callable[[Point2, Point2, float], str]


def polygons(geom: BaseGeometry | None) -> list[Polygon]:
    """The polygon parts of any geometry, ignoring empties, lines and points."""
    if geom is None or geom.is_empty:
        return []
    return [g for g in shapely.get_parts(geom) if isinstance(g, Polygon) and g.area > DEGENERATE]


def clean(geom: BaseGeometry | None) -> BaseGeometry:
    """Put a geometry on the grid and keep only its polygonal parts."""
    if geom is None or geom.is_empty:
        return EMPTY
    parts = polygons(shapely.set_precision(geom, GRID))
    if not parts:
        return EMPTY
    return parts[0] if len(parts) == 1 else shapely.union_all(parts)


def union(geoms: Iterable[BaseGeometry]) -> BaseGeometry:
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    return clean(shapely.union_all(geoms)) if geoms else EMPTY


def triangulate(poly: Polygon) -> list[tuple[Point2, Point2, Point2]]:
    """Triangles covering a polygon (holes allowed), using exactly its ring vertices."""
    triangles = []
    for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(poly)):
        a, b, c = [(float(x), float(y)) for x, y in list(tri.exterior.coords)[:3]]
        if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) > DEGENERATE:
            triangles.append((a, b, c))
    return triangles


def _key(p) -> Point2:
    return (round(float(p[0]), 3), round(float(p[1]), 3))


TOUCH = 0.01  # mm; a vertex this close to a segment was meant to be on it


def pre_noded(lines: list[BaseGeometry]) -> list[LineString]:
    """Every segment of the linework, split at each other vertex lying on it.

    A corner computed to sit on another polygon's edge lands a rounding error
    off it, and GEOS's exact predicates then treat the overlap as a near miss
    and never node it. Splitting at the vertex itself makes such overlaps
    exact, so the union that follows merges them."""
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    for line in lines:
        for part in shapely.get_parts(line):
            coords = shapely.get_coordinates(part)
            segments.extend(zip(coords, coords[1:], strict=False))
    if not segments:
        return []
    vertices = np.unique(np.vstack([np.vstack(s) for s in segments]), axis=0)
    tree = shapely.STRtree(shapely.linestrings([np.vstack(s) for s in segments]))
    points = shapely.points(vertices)
    splits: dict[int, list[np.ndarray]] = {}
    for i, s in zip(*tree.query(points, predicate="dwithin", distance=TOUCH), strict=True):
        v = vertices[i]
        p, q = segments[s]
        if np.allclose(v, p, atol=1e-9) or np.allclose(v, q, atol=1e-9):
            continue
        splits.setdefault(s, []).append(v)
    result = []
    for s, (p, q) in enumerate(segments):
        inner = sorted(splits.get(s, []), key=lambda v: float(np.dot(v - p, q - p)))
        chain = [p, *inner, q]
        result.append(LineString(chain))
    return result


@dataclass
class Arrangement:
    """The cells of a planar subdivision, with each directed edge's owner.

    Cell rings are oriented so the cell lies to the left of every directed
    edge; the reversed edge belongs to the neighbouring cell, or to nothing
    on the outer boundary."""

    cells: list[Polygon]
    owners: dict[tuple[Point2, Point2], int]

    @classmethod
    def of(cls, shapes: Iterable[BaseGeometry]) -> Arrangement:
        return cls.of_lines([s.boundary for s in shapes if s is not None and not s.is_empty])

    @classmethod
    def of_lines(cls, lines: Iterable[BaseGeometry]) -> Arrangement:
        """The cells enclosed by linework, noded and snap-rounded so lines that
        nearly touch (an intersection line ending a hair short of an outline)
        are joined rather than left dangling."""
        lines = [line for line in lines if line is not None and not line.is_empty]
        if not lines:
            return cls([], {})
        # Node, round, and node again: rounding can land a vertex exactly on
        # another line, which set_precision leaves as a T-junction.
        noded = shapely.node(shapely.set_precision(shapely.union_all(pre_noded(lines)), GRID))
        # The polygonizer only joins lines at their ends, and the noded linework
        # comes back merged into runs with junctions as interior vertices; hand
        # it every segment separately so every vertex is a node.
        segments: dict[tuple[Point2, Point2], LineString] = {}
        for line in shapely.get_parts(noded):
            coords = shapely.get_coordinates(line)
            for p, q in zip(coords, coords[1:], strict=False):
                a, b = _key(p), _key(q)
                if a != b:
                    segments.setdefault((a, b) if a < b else (b, a), LineString([a, b]))
        cells = [
            shapely.orient_polygons(c)
            for c in shapely.get_parts(shapely.polygonize(list(segments.values())))
            if c.area > DEGENERATE
        ]
        owners: dict[tuple[Point2, Point2], int] = {}
        for i, cell in enumerate(cells):
            for a, b in cls.edges(cell):
                owners[(a, b)] = i
        return cls(cells, owners)

    @staticmethod
    def edges(cell: Polygon) -> list[tuple[Point2, Point2]]:
        result = []
        for ring in (cell.exterior, *cell.interiors):
            pts = [_key(p) for p in ring.coords[:-1]]
            result.extend(zip(pts, pts[1:] + pts[:1], strict=True))
        return result

    def members(self, polygon: BaseGeometry) -> set[int]:
        """Cells whose interior lies in the polygon."""
        if polygon is None or polygon.is_empty:
            return set()
        prepared = prep(polygon)
        return {i for i, cell in enumerate(self.cells) if prepared.covers(cell.representative_point())}

    def neighbour(self, a: Point2, b: Point2) -> int | None:
        return self.owners.get((b, a))


def build_solid(
    prisms: list[Prism],
    cuts: list[Prism],
    finish_horizontal: HorizontalFinish,
    finish_vertical: VerticalFinish,
    splits: Iterable[BaseGeometry] = (),
) -> list[Face]:
    """Faces of the union of `prisms` minus `cuts`, finishes resolved per face.

    `splits` are extra plan polygons (rooms, say) whose outlines the faces are
    cut along, so a finish can change exactly at them."""
    if not prisms:
        return []
    bottom = min(p.z0 for p in prisms)
    top = max(p.z1 for p in prisms)
    heights = {round(z, 1) for item in (*prisms, *cuts) for z in (item.z0, item.z1)}
    levels = sorted(z for z in heights if bottom - 1e-6 <= z <= top + 1e-6)

    # Inputs go in unrounded: rounding them one by one would put a corner of
    # one a hair off the edge of another, beyond what the noder joins up.
    # The arrangement rounds everything together, once.
    arrangement = Arrangement.of([p.polygon for p in (*prisms, *cuts)] + list(splits))
    prism_cells = [arrangement.members(p.polygon) for p in prisms]
    cut_cells = [arrangement.members(c.polygon) for c in cuts]

    def active(items: list[Prism], za: float, zb: float) -> list[int]:
        return [i for i, p in enumerate(items) if p.z0 <= za + 0.05 and p.z1 >= zb - 0.05]

    bands: list[set[int]] = []
    for za, zb in zip(levels, levels[1:], strict=False):
        cells = set().union(*(prism_cells[i] for i in active(prisms, za, zb)))
        cells -= set().union(*(cut_cells[i] for i in active(cuts, za, zb)))
        bands.append(cells)

    faces: list[Face] = []
    for (za, zb), band in zip(zip(levels, levels[1:], strict=False), bands, strict=True):
        z_mid = (za + zb) / 2
        for i in band:
            for a, b in Arrangement.edges(arrangement.cells[i]):
                other = arrangement.neighbour(a, b)
                if other is not None and other in band:
                    continue
                length = float(np.hypot(b[0] - a[0], b[1] - a[1]))
                if length < DEGENERATE:
                    continue
                outward = ((b[1] - a[1]) / length, -(b[0] - a[0]) / length)  # right of the edge
                finish = finish_vertical(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), outward, z_mid)
                faces.append(Face(((*a, za), (*b, za), (*b, zb), (*a, zb)), finish))

    for k, z in enumerate(levels):
        below = bands[k - 1] if k > 0 else set()
        above = bands[k] if k < len(bands) else set()
        for cells, facing_up in ((below - above, True), (above - below, False)):
            for i in cells:
                cell = arrangement.cells[i]
                inside = cell.representative_point()
                finish = finish_horizontal((inside.x, inside.y), z, facing_up)
                faces.extend(horizontal_faces(cell, z, facing_up, finish))
    return faces


def horizontal_faces(cell: Polygon, z: float, facing_up: bool, finish: str) -> list[Face]:
    faces = []
    for a, b, c in triangulate(cell):
        ccw = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0
        if ccw != facing_up:
            b, c = c, b
        faces.append(Face(((*a, z), (*b, z), (*c, z)), finish))
    return faces
