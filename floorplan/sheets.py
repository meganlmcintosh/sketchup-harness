"""Printable sheets: a storey's plan DXF rendered to scale on paper, as PDF and PNG.

The drawing is placed so 1 mm on paper is exactly `scale` mm in the model, so
a printed PDF can be measured with a scale rule. The PNG is for looking at.
"""

import datetime
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import (  # noqa: E402
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
    LineweightPolicy,
)
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .geometry.storey import ResolvedStorey  # noqa: E402
from .spec import Plan  # noqa: E402
from .units import format_area_m2  # noqa: E402

PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0)}
SCALES = (50, 100, 200, 250, 500)
MARGIN = 10.0
TITLE_W = 95.0
GAP = 5.0
INK = "#1a1a1a"
GRID_INK = "#4a90d9"
DISCLAIMER = "Concept design only. Not for construction.\nVerify all dimensions on site."


@dataclass
class SheetResult:
    pdf: Path
    png: Path
    scale: int


def _fit_scale(extents, draw_w: float, draw_h: float, preferred: int) -> int:
    width, height = extents[2] - extents[0], extents[3] - extents[1]
    for scale in [s for s in SCALES if s >= preferred]:
        if width / scale <= draw_w and height / scale <= draw_h:
            return scale
    return SCALES[-1]


def _grid(ax, extents) -> None:
    x0, y0, x1, y1 = (math.floor(extents[0] / 1000) * 1000, math.floor(extents[1] / 1000) * 1000,
                      math.ceil(extents[2] / 1000) * 1000, math.ceil(extents[3] / 1000) * 1000)  # fmt: skip
    for x in range(int(x0), int(x1) + 1, 1000):
        ax.plot([x, x], [y0, y1], color=GRID_INK, lw=0.3, zorder=0)
        ax.text(x, y0, f"{x / 1000:g}", fontsize=5, color=GRID_INK, ha="center", va="top")
    for y in range(int(y0), int(y1) + 1, 1000):
        ax.plot([x0, x1], [y, y], color=GRID_INK, lw=0.3, zorder=0)
        ax.text(x0, y, f"{y / 1000:g}", fontsize=5, color=GRID_INK, ha="right", va="center")


def render_sheet(
    plan: Plan,
    dxf_path: Path,
    extents: tuple[float, float, float, float],
    title: str,
    sheet_number: str,
    out_stem: Path,
    rs: ResolvedStorey | None = None,
    grid: bool = False,
) -> SheetResult:
    """Render a plan DXF onto a titled sheet; with a storey, include its area schedule.

    grid overlays a labelled 1 m grid in plan coordinates, for checking a plan
    traced from a photo or PDF against its source."""
    import ezdxf

    paper_w, paper_h = PAPER[str(plan.settings.get("sheet", "A3"))]
    draw_w = paper_w - 2 * MARGIN - TITLE_W - GAP
    draw_h = paper_h - 2 * MARGIN
    preferred = int(plan.settings.get("scale", 100))
    scale = _fit_scale(extents, draw_w - 10, draw_h - 10, preferred)

    fig = plt.figure(figsize=(paper_w / 25.4, paper_h / 25.4))

    def mm_rect(x, y, w, h, **kwargs):
        return Rectangle((x / paper_w, y / paper_h), w / paper_w, h / paper_h,
                         transform=fig.transFigure, fill=False, **kwargs)  # fmt: skip

    def mm_text(x, y, text, size, **kwargs):
        kwargs.setdefault("color", INK)
        fig.text(x / paper_w, y / paper_h, text, fontsize=size, **kwargs)

    # Drawing, at exact scale.
    ax = fig.add_axes((MARGIN / paper_w, MARGIN / paper_h, draw_w / paper_w, draw_h / paper_h))
    ax.set_axis_off()
    doc = ezdxf.readfile(dxf_path)
    config = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.COLOR,
        lineweight_policy=LineweightPolicy.ABSOLUTE,
        lineweight_scaling=1.0,
    )
    Frontend(RenderContext(doc), MatplotlibBackend(ax, adjust_figure=False), config=config).draw_layout(
        doc.modelspace(), finalize=True
    )
    cx, cy = (extents[0] + extents[2]) / 2, (extents[1] + extents[3]) / 2
    ax.set_xlim(cx - draw_w * scale / 2, cx + draw_w * scale / 2)
    ax.set_ylim(cy - draw_h * scale / 2, cy + draw_h * scale / 2)
    ax.set_aspect("auto")
    if grid:
        _grid(ax, extents)

    # Border and title block.
    fig.patches.append(mm_rect(MARGIN / 2, MARGIN / 2, paper_w - MARGIN, paper_h - MARGIN, lw=0.6, ec=INK))
    tx = paper_w - MARGIN - TITLE_W
    fig.patches.append(mm_rect(tx, MARGIN, TITLE_W, draw_h, lw=0.4, ec=INK))
    left = tx + 5
    top = paper_h - MARGIN - 10
    project = plan.project
    mm_text(left, top, plan.name.upper(), 13, weight="bold", va="top")
    if project.get("address"):
        mm_text(left, top - 8, str(project["address"]), 7.5, va="top")
    if project.get("client"):
        mm_text(left, top - 13, f"Client: {project['client']}", 7.5, va="top")

    if rs is not None:  # area schedule for this storey
        y = top - 26
        mm_text(left, y, "AREAS", 8, weight="bold", va="top")
        y -= 6
        for room in sorted(rs.rooms, key=lambda r: -r.area):
            mm_text(left, y, room.room.name, 7, va="top")
            mm_text(tx + TITLE_W - 5, y, format_area_m2(room.area), 7, va="top", ha="right")
            y -= 4.6
        y -= 2
        internal = sum(r.area for r in rs.rooms)
        mm_text(left, y, "Rooms total", 7, va="top", weight="bold")
        mm_text(tx + TITLE_W - 5, y, format_area_m2(internal), 7, va="top", ha="right", weight="bold")
        y -= 4.6
        mm_text(left, y, "Floor area (gross)", 7, va="top")
        mm_text(tx + TITLE_W - 5, y, format_area_m2(rs.shell.area), 7, va="top", ha="right")

    # Scale bar: 0-5 m.
    bar_y = MARGIN + 62
    unit = 1000 / scale  # paper mm per metre
    for m in range(5):
        fig.patches.append(
            Rectangle(((left + m * unit) / paper_w, bar_y / paper_h), unit / paper_w, 1.6 / paper_h,
                      transform=fig.transFigure, fc=INK if m % 2 == 0 else "white", ec=INK, lw=0.4)
        )  # fmt: skip
    for m in (0, 1, 5):
        mm_text(left + m * unit, bar_y + 3, f"{m}", 6, ha="center")
    mm_text(left + 5 * unit + 3, bar_y, "m", 6)

    # Sheet details.
    rows = [
        ("Drawing", title),
        ("Scale", f"1:{scale} @ {plan.settings.get('sheet', 'A3')}"),
        ("Date", datetime.date.today().strftime("%d %b %Y")),
        ("Sheet", sheet_number),
    ]
    y = MARGIN + 48
    for label, value in rows:
        mm_text(left, y, label.upper(), 6, color="#666666")
        mm_text(left + 22, y, value, 8, weight="bold" if label == "Drawing" else "normal")
        y -= 6
    mm_text(left, MARGIN + 4, DISCLAIMER, 6, color="#666666")

    pdf, png = out_stem.with_suffix(".pdf"), out_stem.with_suffix(".png")
    fig.savefig(pdf)
    fig.savefig(png, dpi=150)
    plt.close(fig)
    return SheetResult(pdf, png, scale)
