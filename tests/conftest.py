import shutil
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "projects" / "example-townhouse"


@pytest.fixture
def example_project(tmp_path: Path) -> Path:
    """A throwaway copy of the example project, so builds don't touch the repo."""
    project = tmp_path / "example-townhouse"
    project.mkdir()
    shutil.copy(EXAMPLE / "plan.yaml", project / "plan.yaml")
    return project


def edge_report(faces) -> tuple[int, int]:
    """(unmatched directed edges, edges not shared by exactly two faces).

    A closed, consistently oriented, T-junction-free mesh has every directed
    edge a->b matched by exactly one b->a, so both numbers are zero.
    """
    directed = Counter()
    for face in faces:
        pts = [tuple(round(c, 2) for c in p) for p in face.points]
        for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
            directed[(a, b)] += 1
    unmatched = sum(1 for (a, b), n in directed.items() if n != 1 or directed.get((b, a)) != 1)
    undirected = Counter()
    for (a, b), n in directed.items():
        undirected[tuple(sorted((a, b)))] += n
    non_manifold = sum(1 for n in undirected.values() if n != 2)
    return unmatched, non_manifold
