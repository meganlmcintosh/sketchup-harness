"""Furniture, joinery and fixtures at Australian sizes: 3D parts and a plan symbol.

Every design is drawn in its own frame: x across its width, centred on 0;
y from its back (0, the side that goes against a wall) to its front (+depth);
z up from the floor. Placement (furniture.py) turns the front to face the
requested direction. Parts stay at least 1 mm apart, so no two share a face.

Sizes follow common Australian product sizes: mattress sizes (single 920 x
1880 ... king 1830 x 2030), 900 high kitchen benches 600 deep with 350 deep
overheads, 1675 baths, 900 x 900 showers, 600 wide laundry appliances.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box

from .geometry.prism import box_faces, cylinder_faces
from .geometry.solid import Face, Prism, build_solid

GAP = 1.0


@dataclass
class Symbol:
    kind: str  # line | poly | circle | ellipse | text
    points: list[tuple[float, float]] = field(default_factory=list)
    centre: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0  # circle radius, or ellipse semi-major axis along x
    ratio: float = 1.0  # ellipse: semi-minor (along y) / semi-major
    text: str = ""
    closed: bool = True
    dashed: bool = False


@dataclass
class Design:
    label: str  # SketchUp component name
    width: float
    depth: float
    height: float
    faces: list[Face]
    symbols: list[Symbol]
    fixture: bool = False  # joinery and plumbing fixtures draw on A-FLOR-FIXT, furniture on A-FURN


@dataclass
class Entry:
    build: Callable[..., Design]
    params: dict  # parameter -> default
    summary: str


# --- small builders -------------------------------------------------------------


def _box(x0, x1, y0, y1, z0, z1, finish) -> list[Face]:
    return box_faces(x0, x1, y0, y1, z0, z1, finish)


def _rect(x0, y0, x1, y1, dashed=False) -> Symbol:
    return Symbol("poly", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], dashed=dashed)


def _line(a, b, dashed=False) -> Symbol:
    return Symbol("line", [a, b], closed=False, dashed=dashed)


def _circle(cx, cy, r) -> Symbol:
    return Symbol("circle", centre=(cx, cy), radius=r)


def _ellipse(cx, cy, rx, ry) -> Symbol:
    return Symbol("ellipse", centre=(cx, cy), radius=rx, ratio=ry / rx)


def _label(text, cx, cy) -> Symbol:
    return Symbol("text", centre=(cx, cy), text=text)


def _legs(x0, x1, y0, y1, height, finish, size=40.0) -> list[Face]:
    faces = []
    for x in (x0 + GAP, x1 - size - GAP):
        for y in (y0 + GAP, y1 - size - GAP):
            faces += _box(x, x + size, y, y + size, 0, height, finish)
    return faces


def _along(offset: float | None, start: int, width: float) -> float | None:
    """Local x of a point `offset` along a run from its start end.

    start is +1 when the start end is local -x, -1 when it is local +x (the
    placement decides, so offsets always run west-to-east or south-to-north)."""
    if offset is None:
        return None
    return start * (offset - width / 2)


# --- bedroom ----------------------------------------------------------------------

BEDS = {"single": (920, 1880), "king_single": (1070, 2030), "double": (1380, 1880),
        "queen": (1530, 2030), "king": (1830, 2030)}  # fmt: skip


def bed(size: str = "queen", **_) -> Design:
    mattress_w, mattress_l = BEDS[size]
    w, length = mattress_w + 80, mattress_l + 100
    base, top = 350, 600
    faces = _box(-w / 2, w / 2, 0, 60, 0, 1050, "joinery_timber")  # headboard
    faces += _box(-w / 2, w / 2, 61, length, 150, base, "joinery_timber")
    faces += _legs(-w / 2, w / 2, 61, length, 149, "timber_dark", 60)
    faces += _box(-w / 2 + 40, w / 2 - 40, 101, length - 20, base + GAP, top, "linen")
    faces += _box(-w / 2 + 38, w / 2 - 38, length * 0.55, length - 18, top + GAP, top + 25, "fabric_sand")
    pillows = 1 if mattress_w < 1200 else 2
    pillow_w = (w - 80 - 20 * (pillows + 1)) / pillows
    symbols = [_rect(-w / 2, 0, w / 2, length), _line((-w / 2, 60), (w / 2, 60)),
               _line((-w / 2, length * 0.55), (w / 2, length * 0.55)),
               _line((w / 2 - 350, length * 0.55), (w / 2, length * 0.55 + 350))]  # fmt: skip
    for i in range(pillows):
        x0 = -w / 2 + 40 + 20 + i * (pillow_w + 20)
        faces += _box(x0, x0 + pillow_w, 130, 560, top + GAP, top + 140, "linen")
        symbols.append(_rect(x0, 130, x0 + pillow_w, 560))
    label = size.replace("_", " ").title()
    return Design(f"Bed - {label}", w, length, 1050, faces, symbols)


def bedside_table(**_) -> Design:
    w, d = 450, 400
    faces = _box(-w / 2, w / 2, 0, d, 0, 550, "joinery_timber")
    faces += cylinder_faces(0, d / 2, 90, 551, 620, "metal_black", 12)
    faces += cylinder_faces(0, d / 2, 150, 621, 850, "linen", 12)
    return Design("Bedside Table", w, d, 850, faces, [_rect(-w / 2, 0, w / 2, d), _circle(0, d / 2, 150)])


def robe(length: float = 1800, **_) -> Design:
    d, h = 600, 2100
    faces = _box(-length / 2, length / 2, 0, 570, 0, h, "joinery_white")
    faces += _box(-length / 2, -1, 572, 585, 10, h - 10, "joinery_white")
    faces += _box(1, length / 2, 587, 600, 10, h - 10, "joinery_white")
    symbols = [_rect(-length / 2, 0, length / 2, d), _line((-length / 2, 300), (length / 2, 300), dashed=True),
               _line((-length / 2, 578), (0, 578)), _line((0, 593), (length / 2, 593))]  # fmt: skip
    return Design(f"Robe {length:.0f}", length, d, h, faces, symbols, fixture=True)


def tallboy(**_) -> Design:
    w, d, h = 900, 450, 1100
    symbols = [_rect(-w / 2, 0, w / 2, d)]
    return Design("Tallboy", w, d, h, _box(-w / 2, w / 2, 0, d, 0, h, "joinery_timber"), symbols)


def desk(length: float = 1400, **_) -> Design:
    d = 700
    faces = _box(-length / 2, length / 2, 0, d, 700, 740, "joinery_timber")
    faces += _box(-length / 2, -length / 2 + 30, 0, d, 0, 699, "joinery_white")
    faces += _box(length / 2 - 30, length / 2, 0, d, 0, 699, "joinery_white")
    faces += cylinder_faces(0, d + 250, 250, 420, 480, "fabric_grey", 12)  # office chair
    faces += cylinder_faces(0, d + 250, 30, 0, 419, "metal_black", 8)
    faces += _box(-230, 230, d + 460, d + 500, 481, 950, "fabric_grey")
    symbols = [_rect(-length / 2, 0, length / 2, d), _circle(0, d + 250, 250)]
    return Design(f"Desk {length:.0f}", length, d + 500, 950, faces, symbols)


def bookshelf(length: float = 900, **_) -> Design:
    d, h = 350, 1800
    symbols = [_rect(-length / 2, 0, length / 2, d), _line((-length / 2, d), (length / 2, 0))]
    return Design(f"Bookshelf {length:.0f}", length, d, h, _box(-length / 2, length / 2, 0, d, 0, h, "joinery_timber"),
                  symbols)  # fmt: skip


# --- living and dining ------------------------------------------------------------


def sofa(seats: int = 3, chaise: str | None = None, **_) -> Design:
    arm, back, d, seat_w = 200, 220, 950, 700
    w = seats * seat_w + 2 * arm
    fabric, cushion = "fabric_grey", "fabric_sand"
    faces = _box(-w / 2, w / 2, 0, back, 100, 800, fabric)  # back
    faces += _box(-w / 2, -w / 2 + arm, back + GAP, d, 100, 620, fabric)
    faces += _box(w / 2 - arm, w / 2, back + GAP, d, 100, 620, fabric)
    faces += _box(-w / 2 + arm + GAP, w / 2 - arm - GAP, back + GAP, d, 100, 420, fabric)  # seat base
    faces += _legs(-w / 2, w / 2, 0, d, 99, "timber_dark")
    symbols = [
        _rect(-w / 2, 0, w / 2, d),
        _line((-w / 2, back), (w / 2, back)),
        _line((-w / 2 + arm, back), (-w / 2 + arm, d)),
        _line((w / 2 - arm, back), (w / 2 - arm, d)),
    ]
    for i in range(seats):
        x0 = -w / 2 + arm + i * seat_w
        faces += _box(x0 + 2, x0 + seat_w - 2, back + 2, d - 20, 421, 560, cushion)
        if i:
            symbols.append(_line((x0, back), (x0, d)))
    depth, label = d, f"Sofa - {seats} Seat" if seats > 1 else "Armchair"
    if chaise in ("left", "right"):
        sign = 1 if chaise == "right" else -1
        cx0, cx1 = sorted((sign * (w / 2 - arm - seat_w), sign * (w / 2 - arm)))
        faces += _box(cx0 + 2, cx1 - 2, d + GAP, 1700, 100, 420, fabric)
        faces += _box(cx0 + 4, cx1 - 4, d + 2, 1680, 421, 560, cushion)
        faces += _legs(cx0 + 2, cx1 - 2, d + GAP, 1700, 99, "timber_dark")
        symbols.append(_rect(cx0, d, cx1, 1700))
        depth, label = 1700, f"{label} with Chaise"
    return Design(label, w, depth, 800, faces, symbols)


def armchair(**_) -> Design:
    return sofa(seats=1)


def coffee_table(length: float = 1200, **_) -> Design:
    d = 600
    faces = _box(-length / 2, length / 2, 0, d, 381, 420, "joinery_timber") + _legs(-length / 2, length / 2, 0, d, 380,
                                                                                    "timber_dark")  # fmt: skip
    return Design(f"Coffee Table {length:.0f}", length, d, 420, faces, [_rect(-length / 2, 0, length / 2, d)])


def tv_unit(length: float = 1800, **_) -> Design:
    d = 450
    faces = _box(-length / 2, length / 2, 0, d, 0, 500, "joinery_timber")
    faces += _box(-150, 150, 150, 230, 501, 600, "metal_black")  # stand
    faces += _box(-725, 725, 170, 210, 601, 1450, "metal_black")  # 65" screen
    symbols = [_rect(-length / 2, 0, length / 2, d), _line((-725, 190), (725, 190))]
    return Design(f"TV Unit {length:.0f}", length, d, 1450, faces, symbols)


def rug(length: float = 2400, depth: float = 1700, **_) -> Design:
    symbols = [_rect(-length / 2, 0, length / 2, depth, dashed=True)]
    return Design(f"Rug {length:.0f} x {depth:.0f}", length, depth, 8,
                  _box(-length / 2, length / 2, 0, depth, 0, 8, "rug_wool"), symbols)  # fmt: skip


DINING = {4: (1400, 900), 6: (1800, 1000), 8: (2400, 1000)}


def dining_table(seats: int = 6, **_) -> Design:
    if seats not in DINING:
        raise ValueError(f"dining_table seats must be one of {sorted(DINING)}")
    tw, td = DINING[seats]
    reach = 350  # chairs pushed in: seat 150 under the table, 300 out, back 40 beyond that
    d = td + 2 * reach
    y0 = reach
    faces = _box(-tw / 2, tw / 2, y0, y0 + td, 711, 750, "joinery_timber")
    faces += _legs(-tw / 2, tw / 2, y0, y0 + td, 710, "timber_dark", 60)
    symbols = [_rect(-tw / 2, y0, tw / 2, y0 + td)]
    per_side = seats // 2
    spacing = tw / per_side
    for i in range(per_side):
        cx = -tw / 2 + spacing * (i + 0.5)
        for near in (True, False):
            if near:  # the side nearer y = 0: back on the outer (low y) edge
                seat_y0 = y0 - 300
                back = (seat_y0 - 40, seat_y0 - GAP)
            else:
                seat_y0 = y0 + td - 150
                back = (seat_y0 + 450 + GAP, seat_y0 + 490)
            seat_y1 = seat_y0 + 450
            faces += _box(cx - 225, cx + 225, seat_y0, seat_y1, 431, 470, "fabric_sand")
            faces += _box(cx - 225, cx + 225, back[0], back[1], 431, 880, "timber_dark")
            faces += _legs(cx - 225, cx + 225, seat_y0, seat_y1, 430, "timber_dark", 30)
            symbols += [_rect(cx - 225, seat_y0, cx + 225, seat_y1), _rect(cx - 225, back[0], cx + 225, back[1])]
    return Design(f"Dining Table - {seats} Seat", tw, d, 880, faces, symbols)


# --- kitchen ----------------------------------------------------------------------


def kitchen_bench(length: float = 3000, overheads: bool = True, sink: float | None = None,
                  cooktop: float | None = None, start: int = 1, **_) -> Design:  # fmt: skip
    d, top = 600, 900
    faces = _box(-length / 2, length / 2, 0, 510, 0, 149, "metal_black")  # recessed kickboard
    faces += _box(-length / 2, length / 2, 0, 560, 150, 860, "joinery_white")
    faces += _box(-length / 2, length / 2, 0, d, 861, top, "bench_stone")
    symbols = [_rect(-length / 2, 0, length / 2, d)]
    if overheads:
        faces += _box(-length / 2, length / 2, 0, 350, 1500, 2250, "joinery_white")
        symbols.append(_rect(-length / 2, 0, length / 2, 350, dashed=True))
    sx = _along(sink, start, length)
    if sx is not None:
        faces += _box(sx - 400, sx + 400, 100, 550, top + GAP, top + 4, "appliance_steel")
        symbols += [_rect(sx - 400, 100, sx + 400, 550), _circle(sx, 325, 30)]
    cx = _along(cooktop, start, length)
    if cx is not None:
        faces += _box(cx - 300, cx + 300, 50, 550, top + GAP, top + 6, "metal_black")
        faces += _box(cx - 300, cx + 300, 561, 575, 250, 850, "metal_black")  # oven front
        symbols.append(_rect(cx - 300, 50, cx + 300, 550))
        symbols += [_circle(cx + dx, 300 + dy, 90) for dx in (-140, 140) for dy in (-120, 120)]
    return Design(f"Kitchen Bench {length:.0f}", length, d, 2250 if overheads else top, faces, symbols, fixture=True)


def kitchen_island(length: float = 2400, depth: float = 1000, stools: int = 3, sink: float | None = None,
                   cooktop: float | None = None, start: int = 1, **_) -> Design:  # fmt: skip
    carcass, top = depth - 300, 900
    faces = _box(-length / 2, length / 2, 50, carcass - 50, 0, 149, "metal_black")
    faces += _box(-length / 2, length / 2, 0, carcass, 150, 860, "joinery_white")
    faces += _box(-length / 2, length / 2, 0, depth, 861, top, "bench_stone")
    symbols = [_rect(-length / 2, 0, length / 2, depth), _line((-length / 2, carcass), (length / 2, carcass), True)]
    for i in range(stools):
        x = -length / 2 + length / stools * (i + 0.5)
        faces += cylinder_faces(x, depth + 230, 190, 651, 690, "timber_dark", 12)
        faces += cylinder_faces(x, depth + 230, 25, 0, 650, "metal_black", 8)
        symbols.append(_circle(x, depth + 230, 190))
    sx = _along(sink, start, length)
    if sx is not None:
        faces += _box(sx - 400, sx + 400, 100, 550, top + GAP, top + 4, "appliance_steel")
        symbols.append(_rect(sx - 400, 100, sx + 400, 550))
    cx = _along(cooktop, start, length)
    if cx is not None:
        faces += _box(cx - 300, cx + 300, 50, 550, top + GAP, top + 6, "metal_black")
        symbols.append(_rect(cx - 300, 50, cx + 300, 550))
    total_depth = depth + (430 if stools else 0)
    return Design(f"Kitchen Island {length:.0f}", length, total_depth, top, faces, symbols, fixture=True)


def fridge(**_) -> Design:
    w, d, h = 900, 700, 1800
    faces = _box(-w / 2, w / 2, 0, d, 0, h, "appliance_steel")
    faces += _box(-60, -30, d + GAP, d + 40, 800, 1400, "metal_black")
    faces += _box(30, 60, d + GAP, d + 40, 800, 1400, "metal_black")
    return Design("Fridge", w, d + 40, h, faces, [_rect(-w / 2, 0, w / 2, d), _label("REF", 0, d / 2)], fixture=True)


def pantry(length: float = 600, **_) -> Design:
    d, h = 600, 2250
    symbols = [_rect(-length / 2, 0, length / 2, d), _line((-length / 2, 0), (length / 2, d))]
    return Design(f"Pantry {length:.0f}", length, d, h, _box(-length / 2, length / 2, 0, d, 0, h, "joinery_white"),
                  symbols, fixture=True)  # fmt: skip


def cupboard(length: float = 900, depth: float = 600, **_) -> Design:
    h = 2250
    symbols = [_rect(-length / 2, 0, length / 2, depth), _line((-length / 2, 0), (length / 2, depth)),
               _line((-length / 2, depth), (length / 2, 0))]  # fmt: skip
    return Design(f"Cupboard {length:.0f}", length, depth, h,
                  _box(-length / 2, length / 2, 0, depth, 0, h, "joinery_white"), symbols, fixture=True)  # fmt: skip


# --- bathroom and laundry -----------------------------------------------------------


def toilet(**_) -> Design:
    faces = _box(-190, 190, 0, 180, 380, 800, "ceramic_white")  # cistern
    faces += _box(-180, 180, 181, 680, 0, 400, "ceramic_white")  # pan
    faces += _box(-185, 185, 190, 690, 401, 425, "joinery_white")  # seat
    symbols = [_rect(-190, 0, 190, 180), _ellipse(0, 440, 180, 250)]
    return Design("Toilet", 380, 690, 800, faces, symbols, fixture=True)


def vanity(length: float = 900, basins: int = 1, **_) -> Design:
    d = 460
    faces = _box(-length / 2, length / 2, 0, d - 10, 300, 810, "joinery_white")  # wall hung
    faces += _box(-length / 2, length / 2, 0, d, 811, 850, "bench_stone")
    faces += _box(-length / 2, length / 2, 0, 20, 1100, 1900, "glass")  # mirror
    symbols = [_rect(-length / 2, 0, length / 2, d)]
    for i in range(basins):
        x = -length / 2 + length / basins * (i + 0.5)
        faces += cylinder_faces(x, d / 2 + 20, 200, 851, 990, "ceramic_white", 16)
        symbols.append(_ellipse(x, d / 2 + 20, 200, 160))
    return Design(f"Vanity {length:.0f}", length, d, 1900, faces, symbols, fixture=True)


def shower(width: float = 900, depth: float = 900, **_) -> Design:
    faces = _box(-width / 2, width / 2, 0, depth - 12, 0, 30, "ceramic_white")
    faces += _box(-width / 2, width / 2, depth - 10, depth, 31, 2000, "glass")  # front screen
    screen = depth - 10
    symbols = [
        _rect(-width / 2, 0, width / 2, depth),
        _line((-width / 2, 0), (width / 2, screen)),
        _line((width / 2, 0), (-width / 2, screen)),
        _line((-width / 2, screen), (width / 2, screen)),
    ]
    return Design(f"Shower {width:.0f} x {depth:.0f}", width, depth, 2000, faces, symbols, fixture=True)


def bath(length: float = 1675, width: float = 760, **_) -> Design:
    outer = box(-length / 2, 0, length / 2, width)
    inner = box(-length / 2 + 120, 120, length / 2 - 120, width - 120)
    faces = build_solid([Prism(outer, 0, 550)], [Prism(inner, 150, 550)], lambda *_: "ceramic_white",
                        lambda *_: "ceramic_white")  # fmt: skip
    symbols = [_rect(-length / 2, 0, length / 2, width), _rect(-length / 2 + 120, 120, length / 2 - 120, width - 120),
               _circle(length / 2 - 250, width / 2, 30)]  # fmt: skip
    return Design(f"Bath {length:.0f}", length, width, 550, faces, symbols, fixture=True)


def laundry_trough(**_) -> Design:
    w, d = 600, 500
    faces = _box(-w / 2, w / 2, 0, d, 0, 860, "joinery_white") + _box(-w / 2, w / 2, 0, d, 861, 900, "appliance_steel")
    return Design("Laundry Trough", w, d, 900, faces, [_rect(-w / 2, 0, w / 2, d), _rect(-250, 60, 250, 440)],
                  fixture=True)  # fmt: skip


def _appliance(label: str, short: str) -> Callable[..., Design]:
    def build(**_) -> Design:
        w, d, h = 600, 650, 850
        return Design(label, w, d, h, _box(-w / 2, w / 2, 0, d, 0, h, "joinery_white"),
                      [_rect(-w / 2, 0, w / 2, d), _label(short, 0, d / 2)], fixture=True)  # fmt: skip

    return build


# --- other --------------------------------------------------------------------------


def car(**_) -> Design:
    w, d = 1850, 4800
    faces = _box(-w / 2, w / 2, 0, d, 200, 850, "car_paint")
    faces += _box(-w / 2 + 120, w / 2 - 120, 1400, 3700, 851, 1450, "glass")
    for x in (-w / 2 + 80, w / 2 - 330):
        for y in (650, d - 1250):
            faces += _box(x, x + 250, y, y + 650, 0, 199, "metal_black")
    symbols = [Symbol("poly", [(-w / 2, 0), (w / 2, 0), (w / 2, d), (-w / 2, d)], dashed=True)]
    return Design("Car", w, d, 1450, faces, symbols)


def plant(**_) -> Design:
    faces = cylinder_faces(0, 350, 200, 0, 450, "pot_terracotta", 12)
    faces += cylinder_faces(0, 350, 350, 451, 1300, "plant_green", 8)
    return Design("Plant", 700, 700, 1300, faces, [_circle(0, 350, 350), _circle(0, 350, 200)])


CATALOGUE: dict[str, Entry] = {
    "bed": Entry(bed, {"size": "queen"}, "size: single | king_single | double | queen | king"),
    "bedside_table": Entry(bedside_table, {}, "450 x 400 with lamp"),
    "robe": Entry(robe, {"length": 1800}, "built-in robe, 600 deep, sliding doors"),
    "tallboy": Entry(tallboy, {}, "900 x 450 chest of drawers"),
    "desk": Entry(desk, {"length": 1400}, "700 deep, with chair"),
    "bookshelf": Entry(bookshelf, {"length": 900}, "350 deep, 1800 high"),
    "sofa": Entry(sofa, {"seats": 3, "chaise": None}, "seats: 2-4; chaise: left | right"),
    "armchair": Entry(armchair, {}, "single seat"),
    "coffee_table": Entry(coffee_table, {"length": 1200}, "600 deep"),
    "tv_unit": Entry(tv_unit, {"length": 1800}, "450 deep, with 65-inch TV"),
    "rug": Entry(rug, {"length": 2400, "depth": 1700}, "floor rug"),
    "dining_table": Entry(dining_table, {"seats": 6}, "seats: 4 | 6 | 8, chairs included"),
    "kitchen_bench": Entry(kitchen_bench, {"length": 3000, "overheads": True, "sink": None, "cooktop": None},
                           "900 high, 600 deep; sink/cooktop: offset of its centre from the run's start"),  # fmt: skip
    "kitchen_island": Entry(kitchen_island, {"length": 2400, "depth": 1000, "stools": 3, "sink": None, "cooktop": None},
                            "overhang and stools on the front"),  # fmt: skip
    "fridge": Entry(fridge, {}, "900 wide fridge space"),
    "pantry": Entry(pantry, {"length": 600}, "tall cabinet"),
    "cupboard": Entry(cupboard, {"length": 900, "depth": 600}, "full-height storage: linen, garage, built-ins"),
    "toilet": Entry(toilet, {}, "wall-faced pan with cistern"),
    "vanity": Entry(vanity, {"length": 900, "basins": 1}, "wall-hung, with mirror"),
    "shower": Entry(shower, {"width": 900, "depth": 900}, "tray with front glass screen"),
    "bath": Entry(bath, {"length": 1675, "width": 760}, "built-in bath"),
    "laundry_trough": Entry(laundry_trough, {}, "600 x 500 tub and cabinet"),
    "washing_machine": Entry(_appliance("Washing Machine", "WM"), {}, "600 x 650"),
    "dryer": Entry(_appliance("Dryer", "D"), {}, "600 x 650"),
    "car": Entry(car, {}, "4800 x 1850 medium car"),
    "plant": Entry(plant, {}, "potted plant"),
}

# Items whose geometry depends on which end is the run's start (offsets along them).
START_SENSITIVE = {"kitchen_bench", "kitchen_island"}

# Parameters whose values are lengths (accepting "1.8 m" style strings) or counts.
LENGTH_PARAMS = {"length", "depth", "width", "sink", "cooktop"}
INT_PARAMS = {"seats", "stools", "basins"}
BOOL_PARAMS = {"overheads"}
CHOICE_PARAMS = {"size": tuple(BEDS), "chaise": ("left", "right")}


def footprint(design: Design) -> Polygon:
    return box(-design.width / 2, 0, design.width / 2, design.depth)
