from pathlib import Path

import pytest

from viper.core import generate_compose_assets
from viper.exceptions import PortConflictError
from viper.mock_config import default_mock_config
from viper.mock_runtime import prepare_mock_service
from viper.state import State


def test_mock_port_conflicts_with_repo_port(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repos" / "api"
    repo_dir.mkdir(parents=True)
    (repo_dir / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (repo_dir / ".env").write_text("PORT=4010\n", encoding="utf-8")

    state = State(default_stack="localdev", repos=["api"], port_overrides={})
    mock_service = prepare_mock_service(tmp_path, default_mock_config())

    with pytest.raises(PortConflictError):
        generate_compose_assets(
            tmp_path,
            state,
            interactive=False,
            mock_service=mock_service,
        )
