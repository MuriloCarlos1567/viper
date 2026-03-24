from pathlib import Path

import pytest

from viper.exceptions import ValidationError
from viper.mock_config import DEFAULT_MOCK_PORT, default_mock_config, load_mock_config


def test_load_mock_config_valid(tmp_path: Path) -> None:
    config_path = tmp_path / "viper.mock.yaml"
    config_path.write_text(
        "\n".join(
            [
                "server:",
                "  port: 5050",
                "routes:",
                "  - method: GET",
                "    path: /health",
                "    status: 200",
                "    body:",
                "      ok: true",
            ]
        ),
        encoding="utf-8",
    )

    config = load_mock_config(config_path)
    assert config.port == 5050
    assert len(config.routes) == 1
    assert config.routes[0].method == "GET"
    assert config.routes[0].path == "/health"
    assert config.routes[0].status == 200


def test_load_mock_config_invalid_method(tmp_path: Path) -> None:
    config_path = tmp_path / "viper.mock.yaml"
    config_path.write_text(
        "\n".join(
            [
                "routes:",
                "  - method: FETCH",
                "    path: /x",
                "    status: 200",
                "    body: ok",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_mock_config(config_path)


def test_load_mock_config_duplicate_route(tmp_path: Path) -> None:
    config_path = tmp_path / "viper.mock.yaml"
    config_path.write_text(
        "\n".join(
            [
                "routes:",
                "  - method: GET",
                "    path: /users",
                "    status: 200",
                "    body: a",
                "  - method: GET",
                "    path: /users",
                "    status: 404",
                "    body: b",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_mock_config(config_path)


def test_default_mock_config_uses_default_port() -> None:
    config = default_mock_config()
    assert config.port == DEFAULT_MOCK_PORT
    assert config.routes == []
