"""3D doors and windows, as components placed in their wall openings.

Every distinct combination of type, size, sill, wall thickness and hinge side
becomes one DXF block (a SketchUp component definition), shared by every
opening in the house that matches; each opening inserts it.

Block coordinates: x along the wall, centred on the opening; y across the
wall, positive on the wall segment's left (its normal side); z up from FFL.
The insert rotates x onto the segment direction, which keeps y on the left.
A door that opens to the segment's right is the same block turned 180
degrees about the opening's centre: the hinge stays on the same hand.

Hinged doors are modelled open at 90 degrees, matching the swings drawn on
the plans. Every part stays at least GAP clear of the wall and other parts.
"""

import math
from dataclasses import dataclass

from . import au_defaults as au
from .geometry.prism import box_faces, frame, frame_openings
from .geometry.solid import Face
from .geometry.storey import PlacedOpening

GAP = 1.0
WINDOW_BORDER = 50.0
FRAME_DEPTH = 100.0
GLASS = 6.0
LEAF = 35.0
MULLION_FROM = 1200.0  # windows at least this wide get a centre meeting stile
LABELS = {
    "door": "Door",
    "entry_door": "Entry Door",
    "cavity_slider": "Cavity Slider",
    "sliding_door": "Sliding Door",
    "bifold_door": "Bifold Door",
    "garage_door": "Garage Door",
    "window": "Window",
}
HANDED = ("door", "entry_door", "cavity_slider")


@dataclass
class Unit:
    block: str  # DXF block name
    label: str  # SketchUp component name
    faces: list[Face]


@dataclass
class Placement:
    block: str
    at: tuple[float, float, float]
    rotation: float  # degrees, counter-clockwise from +x


def _glass_in(openings, y: float) -> list[Face]:
    return [
        face
        for x0, x1, z0, z1 in openings
        for face in box_faces(x0 + GAP, x1 - GAP, y - GLASS / 2, y + GLASS / 2, z0 + GAP, z1 - GAP, "glass")
    ]


def _window(placed: PlacedOpening) -> list[Face]:
    op, width, thickness = placed.opening, placed.width, placed.segment.thickness
    x0, x1, z0, z1 = -width / 2 + GAP, width / 2 - GAP, op.sill + GAP, op.head - GAP
    half_depth = min(FRAME_DEPTH, thickness - 2 * GAP) / 2
    split = 0.0 if width >= MULLION_FROM else None
    faces = frame(x0, x1, z0, z1, WINDOW_BORDER, -half_depth, half_depth, "frame_dark", split_at=split)
    return faces + _glass_in(frame_openings(x0, x1, z0, z1, WINDOW_BORDER, split_at=split), 0.0)


def _door_frame(placed: PlacedOpening, border: float) -> list[Face]:
    width, head, thickness = placed.width, placed.opening.head, placed.segment.thickness
    half = thickness / 2 - GAP
    return frame(-width / 2 + GAP, width / 2 - GAP, 0.0, head - GAP, border, -half, half, "joinery_white",
                 open_bottom=True)  # fmt: skip


def _hinged(placed: PlacedOpening) -> list[Face]:
    """Built as if opening to the segment's left (side +1); side -1 turns it 180 degrees."""
    op, width, thickness = placed.opening, placed.width, placed.segment.thickness
    hinge = 1 if op.hinge == "left" else -1  # +1: hinge at the +x jamb
    jamb_face = hinge * (width / 2 - au.DOOR_FRAME - GAP)
    leaf_finish = "door_timber" if op.kind == "entry_door" else "door_white"
    face = thickness / 2 + GAP
    leaf = box_faces(jamb_face, jamb_face - hinge * LEAF, face, face + op.width - 2 * GAP, 10.0, op.height + 10.0,
                     leaf_finish)  # fmt: skip
    return _door_frame(placed, au.DOOR_FRAME) + leaf


def _cavity_slider(placed: PlacedOpening) -> list[Face]:
    op = placed.opening
    leaf = box_faces(-op.width / 2 + 2, op.width / 2 - 2, -LEAF / 2, LEAF / 2, 10.0, op.height + 10.0, "door_white")
    return _door_frame(placed, au.DOOR_FRAME) + leaf


def _sliding(placed: PlacedOpening) -> list[Face]:
    op, width, thickness = placed.opening, placed.width, placed.segment.thickness
    half_depth = min(FRAME_DEPTH, thickness - 2 * GAP) / 2
    border = 40.0
    x0, x1, top = -width / 2 + GAP, width / 2 - GAP, op.head - GAP
    faces = frame(x0, x1, 0.0, top, border, -half_depth, half_depth, "frame_dark", open_bottom=True)
    inner0, inner1, panel_top = x0 + border + GAP, x1 - border - GAP, top - border - GAP
    if op.kind == "sliding_door":  # two panels on separate tracks, overlapping at the middle
        panels = [(inner0, 25.0, -half_depth + 5, -5.0), (-25.0, inner1, 5.0, half_depth - 5)]
    else:  # bifold: a row of panels in one plane
        count = max(2, round((inner1 - inner0) / 800))
        step = (inner1 - inner0) / count
        panels = [(inner0 + i * step + GAP, inner0 + (i + 1) * step - GAP, -20.0, 20.0) for i in range(count)]
    for px0, px1, py0, py1 in panels:
        faces += frame(px0, px1, GAP, panel_top, 45.0, py0, py1, "frame_dark")
        faces += _glass_in(frame_openings(px0, px1, GAP, panel_top, 45.0), (py0 + py1) / 2)
    return faces


def _garage(placed: PlacedOpening) -> list[Face]:
    width, head = placed.width, placed.opening.head
    return box_faces(-width / 2 + GAP, width / 2 - GAP, -20.0, 20.0, GAP, head - GAP, "garage_door")


BUILDERS = {
    "window": _window,
    "door": _hinged,
    "entry_door": _hinged,
    "cavity_slider": _cavity_slider,
    "sliding_door": _sliding,
    "bifold_door": _sliding,
    "garage_door": _garage,
}


def unit_key(placed: PlacedOpening) -> tuple:
    op = placed.opening
    hand = op.hinge if op.kind in HANDED else ""
    return (op.kind, round(op.width), round(op.height), round(op.sill), round(placed.segment.thickness), hand)


def unit_for(placed: PlacedOpening) -> Unit:
    """The unit for an opening, named like a schedule entry: type, size, sill if
    unusual, hand, and the wall thickness it is framed for."""
    kind, width, height, sill, thickness, hand = unit_key(placed)
    block = f"{kind.upper()}_{width}x{height}_S{sill}_T{thickness}" + (f"_{hand[0].upper()}H" if hand else "")
    label = f"{LABELS[kind]} {width} x {height}"
    if kind == "window" and sill != round(au.OPENINGS["window"]["head"] - height):
        label += f" sill {sill}"
    if hand:
        label += f" {hand[0].upper()}H"
    return Unit(block, f"{label} ({thickness} wall)", BUILDERS[kind](placed))


def build_units(openings: list[PlacedOpening], ffl: float, units: dict[tuple, Unit]) -> list[Placement]:
    """Placements for a storey's openings; new designs are added to `units` (shared across storeys)."""
    placements = []
    for placed in openings:
        if placed.opening.kind not in BUILDERS:  # a cased opening has no joinery
            continue
        key = unit_key(placed)
        if key not in units:
            units[key] = unit_for(placed)
        cx, cy = placed.centre
        ux, uy = placed.segment.direction
        rotation = math.degrees(math.atan2(uy, ux)) + (180.0 if placed.side < 0 else 0.0)
        placements.append(Placement(units[key].block, (cx, cy, ffl), rotation % 360))
    return placements
