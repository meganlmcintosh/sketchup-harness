"""Small closed solids for components (door leaves, window frames, glass).

Each helper returns a closed, outward-wound set of faces. Parts inside one
component are kept at least 1 mm apart, so SketchUp never sees two of them
sharing a face.
"""

import math

from shapely import orient_polygons
from shapely.geometry import Polygon, box

from .solid import Face, polygons, triangulate


def box_faces(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, finish: str) -> list[Face]:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    quads = [
        ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)),  # bottom
        ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),  # top
        ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),  # -y
        ((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)),  # +y
        ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)),  # -x
        ((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)),  # +x
    ]
    return [Face(q, finish) for q in quads]


def cylinder_faces(cx: float, cy: float, radius: float, z0: float, z1: float, finish: str,
                   sides: int = 16) -> list[Face]:  # fmt: skip
    """A vertical cylinder as a closed prism with `sides` flat faces."""
    ring = [(cx + radius * math.cos(2 * math.pi * i / sides), cy + radius * math.sin(2 * math.pi * i / sides))
            for i in range(sides)]  # fmt: skip
    faces = [
        Face(tuple((x, y, z1) for x, y in ring), finish),  # top, counter-clockwise from above
        Face(tuple((x, y, z0) for x, y in reversed(ring)), finish),
    ]
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1], strict=True):
        faces.append(Face(((ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)), finish))
    return faces


def elevation_prism(profile: Polygon, y0: float, y1: float, finish: str) -> list[Face]:
    """A profile drawn in the x-z plane (x along the wall, z up), extruded
    through the wall from y0 to y1. Used for frames with holes in them."""
    y0, y1 = sorted((y0, y1))
    faces: list[Face] = []
    for poly in polygons(profile):
        for a, b, c in triangulate(poly):
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            # With y fixed, a triangle counter-clockwise in (x, z) faces -y.
            front = (a, b, c) if cross > 0 else (a, c, b)
            faces.append(Face(tuple((x, y0, z) for x, z in front), finish))
            faces.append(Face(tuple((x, y1, z) for x, z in reversed(front)), finish))
        oriented = orient_polygons(poly)  # exterior counter-clockwise in (x, z), holes clockwise
        for ring in (oriented.exterior, *oriented.interiors):
            pts = list(ring.coords)[:-1]
            for (ax, az), (bx, bz) in zip(pts, pts[1:] + pts[:1], strict=True):
                # Material lies left of each edge in (x, z); this winding faces away from it.
                faces.append(Face(((ax, y1, az), (bx, y1, bz), (bx, y0, bz), (ax, y0, az)), finish))
    return faces


def frame(x0: float, x1: float, z0: float, z1: float, border: float, y0: float, y1: float, finish: str,
          open_bottom: bool = False, split_at: float | None = None, mullion: float = 40.0) -> list[Face]:  # fmt: skip
    """A rectangular frame (window sash, door frame) of `border` width.

    open_bottom leaves the bottom rail out (a door frame); split_at adds a
    vertical mullion centred at that x."""
    outer = box(x0, z0, x1, z1)
    hole_bottom = z0 - 1 if open_bottom else z0 + border
    holes = [box(x0 + border, hole_bottom, x1 - border, z1 - border)]
    if split_at is not None:
        half = mullion / 2
        holes = [
            box(x0 + border, hole_bottom, split_at - half, z1 - border),
            box(split_at + half, hole_bottom, x1 - border, z1 - border),
        ]
    profile = outer
    for hole in holes:
        profile = profile.difference(hole)
    return elevation_prism(profile, y0, y1, finish)


Rect = tuple[float, float, float, float]


def frame_openings(x0: float, x1: float, z0: float, z1: float, border: float,
                   split_at: float | None = None, mullion: float = 40.0) -> list[Rect]:  # fmt: skip
    """The clear openings inside `frame`, as (x0, x1, z0, z1)."""
    if split_at is None:
        return [(x0 + border, x1 - border, z0 + border, z1 - border)]
    half = mullion / 2
    return [
        (x0 + border, split_at - half, z0 + border, z1 - border),
        (split_at + half, x1 - border, z0 + border, z1 - border),
    ]
