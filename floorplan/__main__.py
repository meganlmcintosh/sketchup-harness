"""Command line for the floor plan harness. Run through bin/plan:

    ./bin/plan check    projects/<name>   validate and summarise, write nothing
    ./bin/plan build    projects/<name>   write DXFs, PDF/PNG sheets and the manifest
    ./bin/plan sketchup projects/<name>   build, then import into the running SketchUp
    ./bin/plan new      <name|path>       start a project from the template (a bare name goes under projects/)
    ./bin/plan reference                  list wall types, openings, finishes and catalogue items
"""

import argparse
import sys
import time
from pathlib import Path

from .build import BuildResult, build, resolve
from .geometry.storey import ResolvedStorey
from .spec import SpecError
from .units import format_area_m2

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).parent / "template.yaml"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _summarise(storeys: list[ResolvedStorey], stairs=()) -> None:
    for rs in storeys:
        s = rs.storey
        print(f"\n{s.name}  FFL {s.level:.0f}, ceiling {s.height:.0f}, gross {format_area_m2(rs.shell.area)}")
        for room in rs.rooms:
            print(f"  {room.room.name:<30} {format_area_m2(room.area):>9}")
        if rs.unnamed:
            print(f"  ({len(rs.unnamed)} enclosed area(s) without a room name)")
        for stair in stairs:
            if stair.lower is rs:
                going = stair.stair.going
                print(f"  stair to {stair.upper.storey.name}: {stair.risers} risers x {stair.riser:.1f}, "
                      f"going {going:.0f}, 2R+G {2 * stair.riser + going:.0f}")  # fmt: skip
    warnings = [w for rs in storeys for w in rs.warnings]
    for warning in warnings:
        print(f"WARNING {warning}")


def _outputs(result: BuildResult) -> None:
    print("\nWrote:")
    print(f"  {_rel(result.model.path)}")
    for dxf in sorted(result.out.glob("plan-*.dxf")):
        pdf, png = dxf.with_suffix(".pdf"), dxf.with_suffix(".png")
        sheet = next((s for s in result.sheets if s.pdf == pdf), None)
        extra = f", {_rel(pdf)} (1:{sheet.scale}), {_rel(png)}" if sheet else ""
        print(f"  {_rel(dxf)}{extra}")
    print(f"  {_rel(result.manifest)}")


def cmd_check(args) -> None:
    resolved = resolve(args.project)
    _summarise(resolved.storeys, resolved.stairs)
    print("\nOK")


def cmd_build(args) -> None:
    started = time.time()
    result = build(args.project, sheets=not args.no_sheets, grid=args.grid)
    _summarise(result.storeys, result.stairs)
    _outputs(result)
    print(f"Built in {time.time() - started:.1f}s")


def cmd_sketchup(args) -> None:
    from .sketchup import push

    started = time.time()
    result = build(args.project, sheets=not args.no_sheets, grid=args.grid)
    _summarise(result.storeys, result.stairs)
    _outputs(result)
    report = push(result, save=not args.no_save, views=not args.no_views)
    print(f"\nSketchUp: {report.get('faces')} faces, scenes: {', '.join(report.get('scenes', []))}")
    if report.get("saved"):
        print(f"  saved {_rel(Path(report['skp']))}")
    views = sorted((result.out / "views").glob("*.png")) if not args.no_views else []
    for view in views:
        print(f"  view {_rel(view)}")
    for warning in report.get("warnings", []):
        print(f"WARNING {warning}")
    print(f"Done in {time.time() - started:.1f}s")


def cmd_reference(_args) -> None:
    from . import au_defaults as au
    from .catalogue import CATALOGUE
    from .spec import ROOF_DEFAULTS

    print("WALL TYPES (thickness mm, outside / inside finish)")
    for key, wall in au.WALL_TYPES.items():
        print(f"  {key:<18} {wall['thickness']:>4}  {wall['outside']} / {wall['inside']}")
    print("\nOPENINGS (default width x height; hinged doors are leaf sizes)")
    for key, opening in au.OPENINGS.items():
        head = f", head {opening['head']}" if "head" in opening else ""
        print(f"  {key:<14} {opening['width']} x {opening['height']}{head}")
    print("\nSTOREY DEFAULTS")
    print(f"  height {au.STOREY['height']}, ground floor zone {au.STOREY['ground_floor']}, "
          f"upper floor zone {au.STOREY['upper_floor']}")  # fmt: skip
    print("\nROOF TYPES (default pitch, eaves)")
    for key, roof in ROOF_DEFAULTS.items():
        print(f"  {key:<9} {roof['pitch']} deg, {roof['eaves']}")
    print("\nITEMS (type: parameters = defaults; description)")
    for key, entry in CATALOGUE.items():
        params = ", ".join(f"{k}={v}" for k, v in entry.params.items()) or "-"
        print(f"  {key:<16} {params}; {entry.summary}")
    print("\nFINISHES (key: name)")
    for key, finish in au.FINISHES.items():
        print(f"  {key:<16} {finish['name']}")


def cmd_new(args) -> None:
    # A bare name goes under projects/. A path puts the project anywhere else,
    # such as a private repo, so someone's own house stays out of this one.
    is_path = "/" in args.name or args.name.startswith("~")
    project = Path(args.name).expanduser() if is_path else ROOT / "projects" / args.name
    if project.exists():
        sys.exit(f"{_rel(project)} already exists")
    if not project.parent.is_dir():
        sys.exit(f"{_rel(project.parent)} doesn't exist; create it first or check the path")
    (project / "sources").mkdir(parents=True)
    title = project.name.replace("-", " ").title()
    (project / "plan.yaml").write_text(TEMPLATE.read_text().replace("{{name}}", title))
    print(f"Created {_rel(project / 'plan.yaml')}; put briefs, photos and PDFs in {_rel(project / 'sources')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="plan", description="Floor plans to DXF, PDF and SketchUp.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func, text in (
        ("check", cmd_check, "validate a plan and summarise its rooms"),
        ("build", cmd_build, "write DXFs, sheets and the SketchUp manifest"),
        ("sketchup", cmd_sketchup, "build, then import into the running SketchUp"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("project", help="project directory (or its plan.yaml)")
        p.set_defaults(func=func)
        if name != "check":
            p.add_argument("--no-sheets", action="store_true", help="skip PDF/PNG sheets")
            p.add_argument("--grid", action="store_true", help="overlay a 1 m grid on sheets, for checking tracing")
        if name == "sketchup":
            p.add_argument("--no-save", action="store_true", help="don't save the .skp")
            p.add_argument("--no-views", action="store_true", help="don't write scene PNGs")
    p = sub.add_parser("new", help="start a project from the template")
    p.add_argument("name", help="folder name under projects/ (smith-house), or a path to create it elsewhere")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("reference", help="list wall types, openings, finishes and catalogue items")
    p.set_defaults(func=cmd_reference)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except SpecError as exc:
        sys.exit(f"plan.yaml error: {exc}")
    except FileNotFoundError as exc:
        sys.exit(str(exc))
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
