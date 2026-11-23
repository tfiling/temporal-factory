import os
from pathlib import Path

from pydantic import BaseModel


class Labels(BaseModel):
    queue: str
    needs_info: str
    needs_human: str


class Ports(BaseModel):
    base: int = 5100
    step: int = 10


class FactoryConfig(BaseModel):
    ports: Ports = Ports()
    concurrency: int = 3
    max_rounds: int = 3
    base_branch: str = "main"
    merge_method: str = "merge"
    labels: Labels
    models: dict[str, str]
    roles: dict[str, str]
    routing: dict[str, dict[str, str]]
    surface_reviewers: dict[str, dict[str, str]]
    protected_paths: list[str] = []
    checks_cmd: str = "bash /app/checks.sh"


def load_config() -> FactoryConfig:
    path = Path(os.environ.get("FACTORY_CONFIG", Path(__file__).with_name("config.json")))
    cfg = FactoryConfig.model_validate_json(path.read_text())
    if cmd := os.environ.get("FACTORY_CHECKS_CMD"):
        cfg.checks_cmd = cmd
    return cfg


def data_dir() -> Path:
    return Path(os.environ.get("FACTORY_DATA", "/data"))


def target_repo() -> str:
    return os.environ["TARGET_REPO"]
