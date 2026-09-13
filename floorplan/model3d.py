"""3D model DXF for SketchUp: one block (component) per storey element.

Each storey's slab and walls form one closed solid in its own block, so
SketchUp gets separate components that can be hidden per storey (look into
the ground floor with the first floor switched off). Doors and windows are
components of their own, gathered in one block per storey; stairs and
balustrades likewise. Faces are grouped into polyface meshes by finish; the
DXF colour of each is the finish's unique RGB, which the importer turns into
a material that src/floorplan_import.rb renames.

Block contents sit on DXF layer "0" and each block reference on a named layer.
SketchUp turns the layer into the component's tag; the importer puts layer "0"
geometry on a stray tag, which the Ruby import step moves back to Untagged.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import colors
from ezdxf.render import MeshBuilder
from shapely.geometry import Point

from .furniture import PlacedItem
from .geometry.solid import Face, Prism, build_solid
from .geometry.storey import ResolvedStorey
from .openings3d import Unit, build_units
from .roofs import ResolvedRoof, roof_faces
from .spec import Plan
from .stairs import ResolvedStair, balustrade_faces, stair_faces

MAX_POLYFACE_VERTICES = 30_000  # DXF polyface vertex indices are 16-bit
PROBE = 5.0  # mm past a face used to look up what lies in front of it


@dataclass
class ModelLayer:
    layer: str  # DXF layer and block name
    tag: str  # SketchUp tag name
    storey: str | None
    faces: int = 0


@dataclass
class ModelResult:
    path: Path
    layers: list[ModelLayer] = field(default_factory=list)
    definitions: dict[str, str] = field(default_factory=dict)  # DXF block name -> SketchUp component name
    finishes_used: set[str] = field(default_factory=set)


def structure_faces(rs: ResolvedStorey, below: ResolvedStorey | None) -> list[Face]:
    """Slab and walls of one storey, as one conforming solid."""
    storey = rs.storey
    ffl, ceiling, underside = storey.level, storey.level + storey.height, storey.level - storey.floor
    prisms = [Prism(rs.slab, underside, ffl), Prism(rs.walls, ffl, ceiling)]
    cuts = [Prism(o.cut, ffl + o.opening.sill, ffl + o.opening.head) for o in rs.openings]
    cuts += [Prism(void, underside, ffl) for void in rs.voids]
    # Faces are cut along room outlines, so floor and ceiling finishes change exactly at them.
    splits = [r.polygon for r in rs.rooms] + [rs.shell]
    if below is not None:
        splits += [r.polygon for r in below.rooms] + [below.shell]

    def horizontal(point, z: float, facing_up: bool) -> str:
        p = Point(point)
        if facing_up and abs(z - ffl) < 0.5:
            room = rs.room_at(point)
            if room is not None:
                return room.room.floor
            if not rs.rooms or not rs.shell.covers(p):
                return "concrete"  # slab outside the walls
            return min(rs.rooms, key=lambda r: r.polygon.distance(p)).room.floor  # a door threshold
        if not facing_up and abs(z - underside) < 0.5:
            if below is None:
                return "concrete"
            room = below.room_at(point)
            return room.room.ceiling if room is not None else "ceiling_white"
        return "paint_white"  # sills, heads, wall tops

    def vertical(mid, normal, z: float) -> str:
        probe = (mid[0] + normal[0] * PROBE, mid[1] + normal[1] * PROBE)
        point = Point(probe)
        if z < ffl:  # edge of the floor structure
            if below is not None:
                room = below.room_at(probe)
                if room is not None and below.shell.covers(point):
                    return room.room.walls  # e.g. a stair void seen from below
                return rs.nearest_wall(probe).type.outside
            return "concrete"
        inside = rs.shell.covers(point)
        room = rs.room_at(probe)
        if room is not None and inside:  # outdoor rooms (porches) don't repaint the facade
            return room.room.walls
        wall = rs.nearest_wall(probe)
        return wall.type.inside if inside else wall.type.outside

    return build_solid(prisms, cuts, horizontal, vertical, splits)


def add_faces(layout, faces: list[Face], plan: Plan) -> None:
    """Write faces as polyface meshes, one colour per finish."""
    by_finish: dict[str, list[tuple]] = defaultdict(list)
    for face in faces:
        by_finish[face.finish].append(face.points)
    for key, face_points in sorted(by_finish.items()):
        attribs = {"layer": "0", "true_color": colors.rgb2int(plan.finish(key).rgb)}
        chunk: list[tuple] = []
        count = 0
        for points in face_points + [None]:
            if points is None or count + len(points) > MAX_POLYFACE_VERTICES:
                if chunk:
                    mesh = MeshBuilder()
                    for pts in chunk:
                        mesh.add_face(pts)
                    mesh.optimize_vertices(precision=2).render_polyface(layout, dxfattribs=attribs)
                chunk, count = [], 0
            if points is not None:
                chunk.append(points)
                count += len(points)


def item_block(doc, item: PlacedItem, plan: Plan, result: ModelResult) -> str:
    """The component for an item's design, created on first use and shared by identical items."""
    digest = hashlib.sha1(repr(item.key).encode()).hexdigest()[:6]  # stable across runs, unlike hash()
    name = f"ITEM_{item.kind.upper()}_{digest}"
    if name not in doc.blocks:
        add_faces(doc.blocks.new(name), item.design.faces, plan)
        result.definitions[name] = item.design.label
        result.finishes_used.update(f.finish for f in item.design.faces)
    return name


def write_model(plan: Plan, storeys: list[ResolvedStorey], stairs: list[ResolvedStair],
                roofs: list[ResolvedRoof], items: dict[str, list[PlacedItem]], path: Path) -> ModelResult:  # fmt: skip
    doc = ezdxf.new("R2018")
    doc.units = ezdxf.units.MM
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    result = ModelResult(path)

    def place(name: str, tag: str, storey: str | None, count: int) -> None:
        if name not in doc.layers:
            doc.layers.add(name)
        msp.add_blockref(name, (0, 0, 0), dxfattribs={"layer": name})
        result.layers.append(ModelLayer(name, tag, storey, count))

    def add_block(name: str, tag: str, storey: str | None, faces: list[Face]) -> None:
        if not faces:
            return
        add_faces(doc.blocks.new(name), faces, plan)
        result.finishes_used.update(f.finish for f in faces)
        place(name, tag, storey, len(faces))

    units: dict[tuple, Unit] = {}
    for i, rs in enumerate(storeys):
        below = storeys[i - 1] if i > 0 else None
        name, key = rs.storey.name, rs.storey.key
        add_block(f"{key}-STRUCTURE", f"{name} - Structure", name, structure_faces(rs, below))

        placements = build_units(rs.openings, rs.storey.level, units)
        if placements:
            for unit in units.values():
                if unit.block not in doc.blocks:
                    add_faces(doc.blocks.new(unit.block), unit.faces, plan)
                    result.definitions[unit.block] = unit.label
                    result.finishes_used.update(f.finish for f in unit.faces)
            container = doc.blocks.new(f"{key}-OPENINGS")
            for p in placements:
                container.add_blockref(p.block, p.at, dxfattribs={"rotation": p.rotation})
            place(container.name, f"{name} - Doors & Windows", name, len(placements))

        starting_here = [s for s in stairs if s.lower is rs]
        add_block(f"{key}-STAIRS", f"{name} - Stairs", name, [f for s in starting_here for f in stair_faces(s)])
        arriving_here = [s for s in stairs if s.upper is rs]
        add_block(f"{key}-BALUSTRADE", f"{name} - Stairs", name, balustrade_faces(arriving_here))

        placed = items.get(name, [])
        if placed:
            container = doc.blocks.new(f"{key}-FURNITURE")
            for item in placed:
                block = item_block(doc, item, plan, result)
                container.add_blockref(block, (*item.origin, rs.storey.level), dxfattribs={"rotation": item.rotation})
            place(container.name, f"{name} - Furniture", name, len(placed))

    for roof in roofs:
        add_block(f"ROOF-{roof.storey.storey.key}", "Roof", None, roof_faces(roof))

    result.definitions.update({layer.layer: layer.tag for layer in result.layers})
    for roof in roofs:
        result.definitions[f"ROOF-{roof.storey.storey.key}"] = f"Roof over {roof.storey.storey.name}"
    unique_labels(result.definitions)
    doc.saveas(path)
    return result


def unique_labels(definitions: dict[str, str]) -> None:
    """SketchUp uniquifies clashing component names itself, badly ("Robe 1800"
    and "Robe 1800" become "Robe 1800" and "Robe #1"), so number them here."""
    seen: dict[str, int] = {}
    for block, label in list(definitions.items()):
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            definitions[block] = f"{label} ({seen[label]})"
