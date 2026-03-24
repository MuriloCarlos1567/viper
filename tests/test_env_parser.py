from pathlib import Path

import pytest

from viper.env_parser import parse_env_file, read_ports_from_env
from viper.exceptions import EnvParseError


def test_parse_env_file_ignores_comments_and_supports_quotes(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "PORT=8000",
                "NAME='api service'",
                'TOKEN="abc#123"',
                "DEBUG=true # inline comment",
            ]
        ),
        encoding="utf-8",
    )

    data = parse_env_file(env_path)
    assert data["PORT"] == "8000"
    assert data["NAME"] == "api service"
    assert data["TOKEN"] == "abc#123"
    assert data["DEBUG"] == "true"


def test_read_ports_from_env_supports_ports_list(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PORTS=8000, 9000:9001", encoding="utf-8")

    requests = read_ports_from_env(env_path)
    assert [(item.suggested_host_port, item.container_port) for item in requests] == [
        (8000, 8000),
        (9000, 9001),
    ]


def test_read_ports_from_env_requires_port_or_ports(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("APP=api", encoding="utf-8")
    with pytest.raises(EnvParseError):
        read_ports_from_env(env_path)
