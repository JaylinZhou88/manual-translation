from __future__ import annotations

import json
from pathlib import Path

from .models import Project


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"


def ensure_storage() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def project_json_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def save_project(project: Project) -> None:
    ensure_storage()
    project_dir(project.id).mkdir(parents=True, exist_ok=True)
    project_json_path(project.id).write_text(
        project.model_dump_json(indent=2), encoding="utf-8"
    )


def load_project(project_id: str) -> Project:
    path = project_json_path(project_id)
    if not path.exists():
        raise FileNotFoundError(f"Project {project_id} was not found.")
    return Project.model_validate(json.loads(path.read_text(encoding="utf-8")))

