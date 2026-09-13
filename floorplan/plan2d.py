"""2D floor plan DXF, one per storey, drafted the way Australian plans read.

Walls are shown as cut by a horizontal section (default 1200 above FFL) with a
solid fill; doors with swings; windows as frames (dashed when above the cut);
rooms with name, size and area; exterior dimension strings with ticks.

Everything is drawn in model space at full size (mm), in the same coordinates
as the 3D model, so the plan imports into SketchUp directly under the model.
SketchUp drops text and dimensions on import, so their positions are also
returned for the manifest, and the Ruby import step recreates them natively.
"""

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
import shapely
import shapely.ops
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import LineString

from .geometry.solid import clean, polygons
from .geometry.storey import PlacedOpening, ResolvedStorey
from .spec import Plan
from .units import format_area_m2

# Paper sizes in mm; model sizes are these times the plan scale.
PAPER_TEXT = 2.5
PAPER_TEXT_SMALL = 1.8
PAPER_TITLE = 4.0
DIM_CHAIN_OFFSET = 8.0  # paper mm outside the building
DIM_OVERALL_OFFSET = 15.0
WINDOW_FRAME = 50.0  # model mm: depth of the frame drawn inside a window opening
WALL_FILL_RGB = (96, 96, 96)

LAYERS = {
    "A-WALL": {"color": 7, "lineweight": 50},
    "A-WALL-PATT": {"color": 8, "lineweight": 0},
    "A-DOOR": {"color": 7, "lineweight": 25},
    "A-GLAZ": {"color": 7, "lineweight": 18},
    "A-OPEN-ABOV": {"color": 8, "lineweight": 13, "linetype": "DASHED"},
    "A-FLOR-OTLN": {"color": 8, "lineweight": 18},
    "A-FLOR-STRS": {"color": 7, "lineweight": 18},
    "A-FLOR-HRAL": {"color": 7, "lineweight": 25},
    "A-FURN": {"color": 8, "lineweight": 13},
    "A-FLOR-FIXT": {"color": 7, "lineweight": 18},
    "A-ROOF-OTLN": {"color": 8, "lineweight": 18, "linetype": "DASHED"},
    "A-ROOF": {"color": 7, "lineweight": 35},
    "A-ROOF-LINE": {"color": 7, "lineweight": 18},
    "A-AREA-IDEN": {"color": 7, "lineweight": 18},
    "A-ANNO-DIMS": {"color": 7, "lineweight": 13},
    "A-ANNO-TEXT": {"color": 7, "lineweight": 25},
    "A-ANNO-SYMB": {"color": 7, "lineweight": 25},
}


@dataclass
class Label:
    text: str
    at: tuple[float, float]


@dataclass
class Dimension:
    start: tuple[float, float]
    end: tuple[float, float]
    offset: tuple[float, float]  # from the measured points to the dimension line


@dataclass
class PlanResult:
    storey: str
    path: Path
    extents: tuple[float, float, float, float]  # min x, min y, max x, max y (incl. annotation)
    labels: list[Label] = field(default_factory=list)
    dimensions: list[Dimension] = field(default_factory=list)


def _setup(doc, scale: float) -> None:
    for name, attrs in LAYERS.items():
        layer = doc.layers.add(name, color=attrs["color"])
        layer.dxf.lineweight = attrs["lineweight"]
        if "linetype" in attrs:
            layer.dxf.linetype = attrs["linetype"]
    style = doc.dimstyles.new("AU-ARCH")
    style.dxf.dimscale = scale
    style.dxf.dimtxt = PAPER_TEXT_SMALL
    style.dxf.dimtsz = 1.2  # oblique ticks, not arrows
    style.dxf.dimexo = 1.5  # gap between the measured point and the extension line
    style.dxf.dimexe = 1.5  # extension past the dimension line
    style.dxf.dimgap = 0.8
    style.dxf.dimtad = 1  # text above the line
    style.dxf.dimdec = 0
    style.dxf.dimtxsty = "OpenSans"
    style.dxf.dimlwd = 13
    style.dxf.dimlwe = 13


def _text(msp, text: str, at, height: float, align, layer: str, style: str = "OpenSans") -> None:
    msp.add_text(text, height=height, dxfattribs={"layer": layer, "style": style}).set_placement(
        at, align=align
    )


def _angle(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx)) % 360


def _hinged_door(msp, placed: PlacedOpening) -> None:
    seg, op = placed.segment, placed.opening
    side, half_t, leaf = placed.side, seg.thickness / 2, op.width
    # Seen from the room the door opens into, facing the door, "left" runs
    # along the segment in direction side * u (see PlacedOpening.side).
    hinge_dir = side if op.hinge == "left" else -side
    hinge_along = placed.along + hinge_dir * leaf / 2
    hinge = seg.point(hinge_along, side * half_t)
    open_end = seg.point(hinge_along, side * (half_t + leaf))
    closed_end = seg.point(hinge_along - hinge_dir * leaf, side * half_t)
    msp.add_line(hinge, open_end, dxfattribs={"layer": "A-DOOR"})
    a_open = _angle(open_end[0] - hinge[0], open_end[1] - hinge[1])
    a_closed = _angle(closed_end[0] - hinge[0], closed_end[1] - hinge[1])
    start, end = (a_open, a_closed) if (a_closed - a_open) % 360 <= 180 else (a_closed, a_open)
    msp.add_arc(hinge, leaf, start, end, dxfattribs={"layer": "A-DOOR", "lineweight": 13})


def _opening(msp, placed: PlacedOpening, cut_height: float) -> None:
    seg, op = placed.segment, placed.opening
    half_t = seg.thickness / 2
    a0, a1 = placed.along - placed.width / 2, placed.along + placed.width / 2

    def line(along0, across0, along1, across1, layer):
        msp.add_line(seg.point(along0, across0), seg.point(along1, across1), dxfattribs={"layer": layer})

    if op.kind == "window":
        if not placed.cut_by(cut_height):  # above the section: dashed outline only
            for across in (-WINDOW_FRAME / 2, WINDOW_FRAME / 2):
                line(a0, across, a1, across, "A-OPEN-ABOV")
            return
        for across in (-half_t, half_t, -WINDOW_FRAME / 2, WINDOW_FRAME / 2):
            line(a0, across, a1, across, "A-GLAZ")
        for along in (a0, a1):
            line(along, -WINDOW_FRAME / 2, along, WINDOW_FRAME / 2, "A-GLAZ")
    elif op.kind in ("door", "entry_door"):
        _hinged_door(msp, placed)
    elif op.kind in ("sliding_door", "bifold_door"):
        overlap = 50.0
        line(a0, -20, placed.along + overlap, -20, "A-DOOR")
        line(placed.along - overlap, 20, a1, 20, "A-DOOR")
        for along in (a0, a1):
            line(along, -half_t, along, half_t, "A-DOOR")
    elif op.kind == "cavity_slider":
        pocket = 1 if op.hinge == "left" else -1
        start = a0 if pocket < 0 else a1
        line(a0, 0, a1, 0, "A-DOOR")
        line(start, 0, start + pocket * op.width, 0, "A-OPEN-ABOV")
    elif op.kind == "garage_door":
        line(a0, 0, a1, 0, "A-OPEN-ABOV")
    elif op.kind == "opening":
        for across in (-half_t, half_t):
            line(a0, across, a1, across, "A-OPEN-ABOV")


def _obstacles(rs: ResolvedStorey, items, stairs):
    """What a room label should keep clear of: furniture, door swings, stairs and voids."""
    shapes = [item.footprint for item in items]
    for placed in rs.openings:
        if placed.opening.kind in ("door", "entry_door"):
            seg, op, side = placed.segment, placed.opening, placed.side
            hinge_dir = side if op.hinge == "left" else -side
            hinge_along = placed.along + hinge_dir * op.width / 2
            a0, a1 = sorted((hinge_along, hinge_along - hinge_dir * op.width))
            c0, c1 = sorted((side * seg.thickness / 2, side * (seg.thickness / 2 + op.width)))
            shapes.append(seg.rect(a0, a1, c0, c1))
    for stair in stairs:
        if stair.lower is rs:
            shapes.append(stair.footprint)
        if stair.upper is rs:
            shapes.append(stair.void)
    return shapely.union_all([s.buffer(80) for s in shapes]) if shapes else None


CHAR_WIDTH = 0.62  # of the text height, for Open Sans capitals


def _label_box(lines: list[str], scale: float) -> tuple[float, float]:
    """Width and height in model mm of a label: a name line and smaller lines under it."""
    big, small = PAPER_TEXT * scale, PAPER_TEXT_SMALL * scale
    widths = [len(lines[0]) * big * CHAR_WIDTH] + [len(t) * small * CHAR_WIDTH for t in lines[1:]]
    return max(widths), big + (len(lines) - 1) * small * 1.5


def _fit(region, lines: list[str], scale: float) -> tuple[float, float] | None:
    """Where the label fits inside a region, or None if it can't."""
    for poly in sorted(polygons(region), key=lambda p: -p.area):
        w, h = _label_box(lines, scale)
        inner = poly.buffer(-0.5)
        centre = shapely.ops.polylabel(poly, tolerance=10)
        box = shapely.box(centre.x - w / 2, centre.y - h / 2, centre.x + w / 2, centre.y + h / 2)
        if inner.covers(box):
            return (centre.x, centre.y)
        # Try the widest point of a wide region rather than the roundest one.
        slab = clean(poly.buffer(-h / 2))
        for part in polygons(slab):
            minx, _, maxx, _ = part.bounds
            if maxx - minx >= w:
                p = shapely.ops.polylabel(part, tolerance=10)
                box = shapely.box(p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2)
                if inner.covers(box):
                    return (p.x, p.y)
    return None


def _place_label(room, obstacles, lines: list[str], scale: float) -> tuple[tuple[float, float], list[str]]:
    """A spot for the label clear of fixtures and door swings, shortening the
    label (size line, then area) when the room is too small for all of it."""
    if room.room.label_at:
        return room.room.label_at, lines
    free = room.polygon.buffer(-150).difference(obstacles) if obstacles is not None else room.polygon.buffer(-150)
    for candidate in (lines, lines[:1] + lines[-1:], lines[:1]):
        for region in (free, room.polygon.buffer(-150)):
            at = _fit(region, candidate, scale)
            if at is not None:
                return at, candidate
    return room.label_point, lines[:1]


def _room_labels(msp, rs: ResolvedStorey, scale: float, items=(), stairs=()) -> list[Label]:
    labels = []
    big, small = PAPER_TEXT * scale, PAPER_TEXT_SMALL * scale
    obstacles = _obstacles(rs, items, stairs)
    for room in rs.rooms:
        minx, miny, maxx, maxy = room.polygon.bounds
        lines = [room.room.name.upper()]
        if room.area >= 0.97 * (maxx - minx) * (maxy - miny):  # rectangular: give its size
            lines.append(f"{(maxx - minx) / 1000:.1f} × {(maxy - miny) / 1000:.1f}")
        lines.append(format_area_m2(room.area))
        (x, y), lines = _place_label(room, obstacles, lines, scale)
        top = y + (len(lines) - 1) * small * 0.8
        _text(msp, lines[0], (x, top), big, TextEntityAlignment.MIDDLE_CENTER, "A-AREA-IDEN", "OpenSans-SemiBold")
        for i, text in enumerate(lines[1:], start=1):
            _text(msp, text, (x, top - big * 0.4 - i * small * 1.5 + small * 0.5), small,
                  TextEntityAlignment.MIDDLE_CENTER, "A-AREA-IDEN")  # fmt: skip
        labels.append(Label("\n".join(lines), (x, y)))
    return labels


def _arrow(msp, points: list[tuple[float, float]], text: str, scale: float) -> Label:
    """An arrow along `points`, optionally labelled at its start (UP / DN)."""
    msp.add_lwpolyline(points, dxfattribs={"layer": "A-FLOR-STRS"})
    (x0, y0), (x1, y1) = points[-2], points[-1]
    length = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    size = 1.5 * scale
    head = [(x1, y1), (x1 - ux * size * 2 - uy * size, y1 - uy * size * 2 + ux * size),
            (x1 - ux * size * 2 + uy * size, y1 - uy * size * 2 - ux * size)]  # fmt: skip
    msp.add_solid(head, dxfattribs={"layer": "A-FLOR-STRS"})
    sx, sy = points[0]
    (ax, ay), (bx, by) = points[0], points[1]
    seg = math.hypot(bx - ax, by - ay) or 1.0
    at = (sx - (bx - ax) / seg * 2.5 * scale, sy - (by - ay) / seg * 2.5 * scale)
    if text:
        _text(msp, text, at, PAPER_TEXT_SMALL * scale, TextEntityAlignment.MIDDLE_CENTER, "A-FLOR-STRS",
              "OpenSans-SemiBold")  # fmt: skip
    return Label(text, at)


def _stairs(msp, rs: ResolvedStorey, stairs, cut_height: float, scale: float) -> list[Label]:
    labels = []
    for stair in stairs:
        treads = stair.treads
        if stair.lower is rs:
            above = [t.top > cut_height for t in treads]
            for tread, is_above in zip(treads, above, strict=True):
                ring = list(tread.polygon.exterior.coords)
                msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "A-OPEN-ABOV" if is_above else "A-FLOR-STRS"})
            cut = next((i for i, a in enumerate(above) if a), len(treads))
            if cut < len(treads):  # break line across the first tread above the section
                corners = list(treads[cut].polygon.exterior.coords)
                msp.add_line(corners[0], corners[2], dxfattribs={"layer": "A-FLOR-STRS"})
            walk = [tuple(treads[0].nosing.interpolate(0.5, normalized=True).coords[0])]
            walk += [(t.polygon.centroid.x, t.polygon.centroid.y) for t in treads[: max(cut, 1)]]
            labels.append(_arrow(msp, walk, "UP", scale))
        if stair.upper is rs:
            for poly in polygons(stair.void):
                msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": "A-FLOR-OTLN"})
            visible = [t for t in treads if t.polygon.intersects(stair.void)]
            for tread in visible:
                for part in polygons(tread.polygon.intersection(stair.void)):
                    msp.add_lwpolyline(list(part.exterior.coords), close=True, dxfattribs={"layer": "A-FLOR-STRS"})
            for strip in stair.balustrade:
                msp.add_lwpolyline(list(strip.exterior.coords), close=True, dxfattribs={"layer": "A-FLOR-HRAL"})
            walk = [tuple(stair.arrival.interpolate(0.5, normalized=True).coords[0])]
            walk += [(t.polygon.centroid.x, t.polygon.centroid.y) for t in reversed(visible)]
            if len(walk) >= 2:
                labels.append(_arrow(msp, walk, "DN", scale))
    return labels


def _dimensions(msp, rs: ResolvedStorey, scale: float) -> list[Dimension]:
    """Chain and overall dimensions along the south and east sides of the building.

    They measure the walls (the shell) but sit outside everything on the slab,
    so a porch or deck doesn't collide with them."""
    shell = max(polygons(rs.shell), key=lambda p: p.area)
    minx, miny, maxx, maxy = shell.bounds
    _, slab_miny, slab_maxx, _ = rs.slab.bounds
    coords = list(shell.exterior.coords)
    dims: list[Dimension] = []
    chain_off, overall_off = DIM_CHAIN_OFFSET * scale, DIM_OVERALL_OFFSET * scale

    xs = sorted({round(x, 1) for x, _ in coords})
    ys = sorted({round(y, 1) for _, y in coords})
    for values, horizontal in ((xs, True), (ys, False)):
        strings = [(values, chain_off)] if len(values) > 2 else []
        strings.append(([values[0], values[-1]], overall_off if len(values) > 2 else chain_off))
        for points, off in strings:
            if horizontal:
                pts = [(v, miny) for v in points]
                base = (points[0], slab_miny - off)
                offset = (0.0, slab_miny - off - miny)
            else:
                pts = [(maxx, v) for v in points]
                base = (slab_maxx + off, points[0])
                offset = (slab_maxx + off - maxx, 0.0)
            msp.add_multi_point_linear_dim(
                base=base, points=pts, angle=0 if horizontal else 90, dimstyle="AU-ARCH",
                dxfattribs={"layer": "A-ANNO-DIMS"},
            )  # fmt: skip
            dims.extend(Dimension(a, b, offset) for a, b in zip(pts, pts[1:], strict=False))
    return dims


def _north_arrow(msp, at: tuple[float, float], north_deg: float, scale: float) -> None:
    r = 6.0 * scale
    x, y = at
    msp.add_circle(at, r, dxfattribs={"layer": "A-ANNO-SYMB"})
    theta = math.radians(90 - north_deg)
    tip = (x + math.cos(theta) * r * 1.3, y + math.sin(theta) * r * 1.3)
    left = (x + math.cos(theta + 2.6) * r * 0.7, y + math.sin(theta + 2.6) * r * 0.7)
    right = (x + math.cos(theta - 2.6) * r * 0.7, y + math.sin(theta - 2.6) * r * 0.7)
    hatch = msp.add_hatch(color=7, dxfattribs={"layer": "A-ANNO-SYMB"})
    hatch.paths.add_polyline_path([tip, left, (x, y), right], is_closed=True)
    label_at = (x + math.cos(theta) * r * 1.9, y + math.sin(theta) * r * 1.9)
    _text(msp, "N", label_at, PAPER_TEXT * scale, TextEntityAlignment.MIDDLE_CENTER, "A-ANNO-SYMB", "OpenSans-Bold")


def _new_doc(scale: float):
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$MEASUREMENT"] = 1
    _setup(doc, scale)
    return doc


def write_plan(plan: Plan, rs: ResolvedStorey, path: Path, stairs=(), roofs=(), items=()) -> PlanResult:
    scale = float(plan.settings["scale"])
    cut_height = float(plan.settings["cut_height"])
    doc = _new_doc(scale)
    msp = doc.modelspace()

    for extension in rs.storey.slab_extensions:
        msp.add_lwpolyline(extension, close=True, dxfattribs={"layer": "A-FLOR-OTLN"})
    for roof in roofs:  # eaves above this storey, dashed
        if roof.storey is rs:
            for poly in polygons(roof.footprint):
                msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": "A-ROOF-OTLN"})

    for poly in polygons(rs.plan_cut(cut_height)):
        rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]
        fill = msp.add_hatch(dxfattribs={"layer": "A-WALL-PATT"})
        fill.rgb = WALL_FILL_RGB
        for i, ring in enumerate(rings):
            fill.paths.add_polyline_path(ring, is_closed=True, flags=1 if i == 0 else 0)
            msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "A-WALL"})

    for placed in rs.openings:
        _opening(msp, placed, cut_height)

    result = PlanResult(rs.storey.name, path, (0, 0, 0, 0))
    _furniture(doc, msp, items)
    result.labels = _room_labels(msp, rs, scale, items, stairs) + _stairs(msp, rs, stairs, cut_height, scale)
    result.dimensions = _dimensions(msp, rs, scale)

    minx, miny, maxx, maxy = rs.slab.bounds
    title_y = miny - (DIM_OVERALL_OFFSET + 12) * scale
    _text(msp, f"{rs.storey.name.upper()} PLAN", (minx, title_y), PAPER_TITLE * scale,
          TextEntityAlignment.LEFT, "A-ANNO-TEXT", "OpenSans-Bold")  # fmt: skip
    _text(msp, f"SCALE 1:{scale:.0f}", (minx, title_y - PAPER_TITLE * scale * 1.6), PAPER_TEXT * scale,
          TextEntityAlignment.LEFT, "A-ANNO-TEXT")  # fmt: skip
    _north_arrow(msp, (maxx + (DIM_OVERALL_OFFSET + 14) * scale, maxy - 8 * scale),
                 float(plan.project.get("north", 0)), scale)  # fmt: skip

    result.extents = (
        minx - 2 * scale,
        title_y - PAPER_TITLE * scale * 2.2,
        maxx + (DIM_OVERALL_OFFSET + 24) * scale,
        maxy + 4 * scale,
    )
    doc.saveas(path)
    return result


def write_roof_plan(plan: Plan, storeys: list[ResolvedStorey], roofs, path: Path) -> PlanResult:
    """Roof plan: eaves outline, hips, ridges and valleys, fall arrows with pitch, walls below dashed."""
    scale = float(plan.settings["scale"])
    doc = _new_doc(scale)
    msp = doc.modelspace()
    result = PlanResult("Roof", path, (0, 0, 0, 0))

    for rs in storeys:
        if any(roof.storey is rs for roof in roofs):
            for poly in polygons(rs.shell):
                msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": "A-ROOF-OTLN"})
    bounds = []
    for roof in roofs:
        bounds.append(roof.footprint.bounds)
        for poly in polygons(roof.footprint):
            msp.add_lwpolyline(list(poly.exterior.coords), close=True, dxfattribs={"layer": "A-ROOF"})
        edges = set()
        for piece in roof.pieces:
            ring = [tuple(round(c, 1) for c in p) for p in piece.polygon.exterior.coords]
            for a, b in zip(ring, ring[1:], strict=False):
                edges.add(tuple(sorted((a, b))))
        boundary = roof.footprint.boundary.buffer(1)
        for a, b in edges:
            if not boundary.covers(LineString([a, b])):  # hips, ridges and valleys
                msp.add_line(a, b, dxfattribs={"layer": "A-ROOF-LINE"})
        for piece in roof.pieces:
            if piece.plane is None or piece.polygon.area < 1e6:
                continue
            centre = piece.polygon.representative_point()
            gx, gy = piece.plane.a, piece.plane.b
            size = math.hypot(gx, gy)
            if size < 1e-9:
                continue
            ux, uy = -gx / size, -gy / size  # downhill
            length = min(1500.0, math.sqrt(piece.polygon.area) * 0.4)
            start = (centre.x - ux * length / 2, centre.y - uy * length / 2)
            end = (centre.x + ux * length / 2, centre.y + uy * length / 2)
            _arrow(msp, [start, end], "", scale)
            pitch = math.degrees(math.atan(size))
            _text(msp, f"{pitch:.1f}°", (centre.x - uy * 2.5 * scale, centre.y + ux * 2.5 * scale),
                  PAPER_TEXT_SMALL * scale, TextEntityAlignment.MIDDLE_CENTER, "A-ROOF-LINE")  # fmt: skip

    minx = min(b[0] for b in bounds)
    miny = min(b[1] for b in bounds)
    maxx = max(b[2] for b in bounds)
    maxy = max(b[3] for b in bounds)
    title_y = miny - 14 * scale
    _text(msp, "ROOF PLAN", (minx, title_y), PAPER_TITLE * scale, TextEntityAlignment.LEFT, "A-ANNO-TEXT",
          "OpenSans-Bold")  # fmt: skip
    _text(msp, f"SCALE 1:{scale:.0f}", (minx, title_y - PAPER_TITLE * scale * 1.6), PAPER_TEXT * scale,
          TextEntityAlignment.LEFT, "A-ANNO-TEXT")  # fmt: skip
    _north_arrow(msp, (maxx + 14 * scale, maxy - 8 * scale), float(plan.project.get("north", 0)), scale)
    result.extents = (minx - 2 * scale, title_y - PAPER_TITLE * scale * 2.2, maxx + 24 * scale, maxy + 4 * scale)
    doc.saveas(path)
    return result


FURNITURE_TEXT = 150.0  # model mm; small labels inside symbols (REF, WM)


def _furniture(doc, msp, items) -> None:
    """Items as block references, one block per design, so CAD users can move them."""
    for item in items:
        design = item.design
        digest = hashlib.sha1(repr(item.key).encode()).hexdigest()[:6]
        name = f"SYM_{item.kind.upper()}_{digest}"
        if name not in doc.blocks:
            block = doc.blocks.new(name)
            for symbol in design.symbols:
                attribs = {"linetype": "DASHED"} if symbol.dashed else {}
                if symbol.kind == "poly":
                    block.add_lwpolyline(symbol.points, close=symbol.closed, dxfattribs=attribs)
                elif symbol.kind == "line":
                    block.add_line(symbol.points[0], symbol.points[1], dxfattribs=attribs)
                elif symbol.kind == "circle":
                    block.add_circle(symbol.centre, symbol.radius, dxfattribs=attribs)
                elif symbol.kind == "ellipse":  # DXF needs the major axis to be the longer one
                    if symbol.ratio <= 1:
                        major, ratio = (symbol.radius, 0), symbol.ratio
                    else:
                        major, ratio = (0, symbol.radius * symbol.ratio), 1 / symbol.ratio
                    block.add_ellipse(symbol.centre, major_axis=major, ratio=ratio, dxfattribs=attribs)
        layer = "A-FLOR-FIXT" if design.fixture else "A-FURN"
        msp.add_blockref(name, item.origin, dxfattribs={"layer": layer, "rotation": item.rotation})
        # Text goes in model space, not the shared block, so it can stay upright whichever way the item faces.
        theta = math.radians(item.bearing)
        right, front = (math.cos(theta), -math.sin(theta)), (math.sin(theta), math.cos(theta))
        upright = item.rotation % 360
        if 90 < upright <= 270:
            upright -= 180
        for symbol in design.symbols:
            if symbol.kind == "text":
                u, v = symbol.centre
                at = (item.origin[0] + right[0] * u + front[0] * v, item.origin[1] + right[1] * u + front[1] * v)
                text = msp.add_text(symbol.text, height=FURNITURE_TEXT,
                                    dxfattribs={"layer": layer, "style": "OpenSans", "rotation": upright})  # fmt: skip
                text.set_placement(at, align=TextEntityAlignment.MIDDLE_CENTER)
