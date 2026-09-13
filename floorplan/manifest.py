"""sketchup.json: everything src/floorplan_import.rb needs that the DXFs can't carry.

The importer drops text, dimensions and transparency, and names materials
"<auto>N"; this manifest supplies labels, dimensions, material names/alpha
and the DXF-layer to SketchUp-tag mapping.
"""

import json
from pathlib import Path

from .geometry.storey import ResolvedStorey
from .model3d import ModelResult
from .plan2d import WALL_FILL_RGB, PlanResult
from .spec import Plan

# Linework colours in the plan DXFs (ACI 7 imports as white, ACI 8 as grey).
PLAN_MATERIALS = [
    {"rgb": [255, 255, 255], "name": "Plan - Linework", "alpha": 1.0},
    {"rgb": [128, 128, 128], "name": "Plan - Grey Linework", "alpha": 1.0},
    {"rgb": list(WALL_FILL_RGB), "name": "Plan - Wall Fill", "alpha": 1.0},
    # SketchUp gives the labels and dimensions the import step adds this default grey.
    {"rgb": [63, 63, 63], "name": "Plan - Annotation", "alpha": 1.0},
]

MANIFEST_VERSION = 1


def slug(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def write_manifest(
    plan: Plan,
    storeys: list[ResolvedStorey],
    model: ModelResult,
    plans: list[PlanResult],
    path: Path,
) -> dict:
    project_id = slug(plan.source.parent.name if plan.source else plan.name)
    data = {
        "version": MANIFEST_VERSION,
        "project": plan.name,
        "project_id": project_id,
        "units": "mm",
        "model": {
            "dxf": str(model.path.resolve()),
            "layers": [
                {"layer": layer.layer, "tag": layer.tag, "storey": layer.storey} for layer in model.layers
            ],
            "tags": list(dict.fromkeys(layer.tag for layer in model.layers)),
            "definitions": model.definitions,
        },
        "plans": [
            {
                "storey": result.storey,
                "dxf": str(result.path.resolve()),
                "tag": f"{result.storey} - Plan",
                "level": rs.storey.level,
                "labels": [{"text": label.text, "at": list(label.at)} for label in result.labels],
                "dimensions": [
                    {"start": list(d.start), "end": list(d.end), "offset": list(d.offset)}
                    for d in result.dimensions
                ],
            }
            for result, rs in zip(plans, storeys, strict=True)
        ],
        "storeys": [
            {
                "name": rs.storey.name,
                "level": rs.storey.level,
                "height": rs.storey.height,
                "tags": list(dict.fromkeys(layer.tag for layer in model.layers if layer.storey == rs.storey.name)),
            }
            for rs in storeys
        ],
        "materials": [
            {"rgb": list(f.rgb), "name": f.name, "alpha": f.alpha} for f in plan.finishes.values()
        ]
        + PLAN_MATERIALS,
    }
    path.write_text(json.dumps(data, indent=2))
    return data
