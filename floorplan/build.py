"""Build a project: plan.yaml -> out/ (DXFs, PDF and PNG sheets, sketchup.json)."""

from dataclasses import dataclass
from pathlib import Path

from .furniture import PlacedItem, place_items
from .geometry.storey import ResolvedStorey, resolve_storey
from .manifest import slug, write_manifest
from .model3d import ModelResult, write_model
from .plan2d import PlanResult, write_plan, write_roof_plan
from .roofs import ResolvedRoof, resolve_roofs
from .sheets import SheetResult, render_sheet
from .spec import Plan, load_plan
from .stairs import ResolvedStair, resolve_stairs

GENERATED = ("model.dxf", "sketchup.json", "plan-*.dxf", "plan-*.pdf", "plan-*.png")


@dataclass
class Resolved:
    plan: Plan
    storeys: list[ResolvedStorey]
    stairs: list[ResolvedStair]
    roofs: list[ResolvedRoof]
    items: dict[str, list[PlacedItem]]


@dataclass
class BuildResult:
    plan: Plan
    storeys: list[ResolvedStorey]
    stairs: list[ResolvedStair]
    roofs: list[ResolvedRoof]
    out: Path
    model: ModelResult
    plans: list[PlanResult]
    sheets: list[SheetResult]
    manifest: Path

    @property
    def project_id(self) -> str:
        return slug(self.out.parent.name)

    @property
    def warnings(self) -> list[str]:
        return [w for rs in self.storeys for w in rs.warnings]


def resolve(project: str | Path) -> Resolved:
    plan = load_plan(project)
    storeys = [resolve_storey(storey) for storey in plan.storeys]
    stairs = resolve_stairs(storeys)
    roofs = resolve_roofs(plan.roofs, storeys)
    items = {rs.storey.name: place_items(rs) for rs in storeys}
    return Resolved(plan, storeys, stairs, roofs, items)


def build(project: str | Path, sheets: bool = True, grid: bool = False) -> BuildResult:
    resolved = resolve(project)
    plan, storeys, stairs, roofs = resolved.plan, resolved.storeys, resolved.stairs, resolved.roofs
    out = plan.source.parent / "out"
    out.mkdir(exist_ok=True)
    for pattern in GENERATED:  # a renamed storey must not leave its old sheets behind
        for stale in out.glob(pattern):
            stale.unlink()

    items = resolved.items
    model = write_model(plan, storeys, stairs, roofs, items, out / "model.dxf")
    plans, sheet_results = [], []
    for i, rs in enumerate(storeys):
        stem = out / f"plan-{slug(rs.storey.name)}"
        result = write_plan(plan, rs, stem.with_suffix(".dxf"), stairs, roofs, items[rs.storey.name])
        plans.append(result)
        if sheets:
            title, number = f"{rs.storey.name} Plan", f"A-{101 + i}"
            sheet_results.append(render_sheet(plan, result.path, result.extents, title, number, stem, rs, grid))
    if roofs:
        stem = out / "plan-roof"
        roof_plan = write_roof_plan(plan, storeys, roofs, stem.with_suffix(".dxf"))
        if sheets:
            number = f"A-{101 + len(storeys)}"
            sheet_results.append(render_sheet(plan, roof_plan.path, roof_plan.extents, "Roof Plan", number, stem,
                                              grid=grid))  # fmt: skip
    manifest = out / "sketchup.json"
    write_manifest(plan, storeys, model, plans, manifest)
    return BuildResult(plan, storeys, stairs, roofs, out, model, plans, sheet_results, manifest)
