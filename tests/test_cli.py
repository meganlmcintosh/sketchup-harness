import pytest

from floorplan import __main__ as cli
from floorplan.build import resolve


def test_new_at_a_path_starts_a_valid_project_there(tmp_path):
    project = tmp_path / "smith-house"
    cli.main(["new", str(project)])
    assert (project / "sources").is_dir()
    assert "name: Smith House" in (project / "plan.yaml").read_text()
    assert resolve(project).storeys  # the template is a plan that resolves


def test_new_with_a_bare_name_goes_under_projects(tmp_path, monkeypatch):
    (tmp_path / "projects").mkdir()
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    cli.main(["new", "smith-house"])
    assert (tmp_path / "projects" / "smith-house" / "plan.yaml").is_file()


def test_new_refuses_an_existing_folder_or_a_missing_parent(tmp_path):
    with pytest.raises(SystemExit, match="already exists"):
        cli.main(["new", str(tmp_path)])
    with pytest.raises(SystemExit, match="doesn't exist"):
        cli.main(["new", str(tmp_path / "typo" / "smith-house")])
    assert not (tmp_path / "typo").exists()
