from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from viper.exceptions import ValidationError


DEFAULT_MOCK_PORT = 4010
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class MockRoute:
    method: str
    path: str
    status: int
    body: object


@dataclass(frozen=True)
class MockConfig:
    port: int
    routes: list[MockRoute]


def load_mock_config(path: Path, *, port_override: int | None = None) -> MockConfig:
    if not path.exists():
        raise ValidationError(f"Arquivo de mock nao encontrado: {path}")

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValidationError(f"YAML invalido em {path}: {error}") from error

    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValidationError(f"Config de mock deve ser um objeto YAML: {path}")

    if "routes" not in loaded:
        raise ValidationError(f"Campo obrigatorio ausente em {path}: routes")
    routes_raw = loaded.get("routes")
    if not isinstance(routes_raw, list):
        raise ValidationError(f"Campo routes deve ser lista em {path}")

    server_raw = loaded.get("server", {})
    if server_raw is None:
        server_raw = {}
    if not isinstance(server_raw, dict):
        raise ValidationError(f"Campo server deve ser objeto em {path}")

    port = _parse_port(server_raw.get("port", DEFAULT_MOCK_PORT), field_name="server.port")
    if port_override is not None:
        port = _parse_port(port_override, field_name="--port")

    routes: list[MockRoute] = []
    seen: set[tuple[str, str]] = set()
    for index, route_raw in enumerate(routes_raw):
        if not isinstance(route_raw, dict):
            raise ValidationError(f"routes[{index}] deve ser objeto")

        method = str(route_raw.get("method", "")).strip().upper()
        path_value = str(route_raw.get("path", "")).strip()
        status = route_raw.get("status")

        if not method:
            raise ValidationError(f"routes[{index}].method e obrigatorio")
        if method not in SUPPORTED_METHODS:
            raise ValidationError(f"routes[{index}].method invalido: {method}")
        if not path_value or not path_value.startswith("/"):
            raise ValidationError(f"routes[{index}].path deve comecar com '/'")
        if status is None:
            raise ValidationError(f"routes[{index}].status e obrigatorio")
        status_code = _parse_status(status, field_name=f"routes[{index}].status")

        key = (method, path_value)
        if key in seen:
            raise ValidationError(f"Rota duplicada: {method} {path_value}")
        seen.add(key)

        routes.append(
            MockRoute(
                method=method,
                path=path_value,
                status=status_code,
                body=route_raw.get("body"),
            )
        )

    return MockConfig(port=port, routes=routes)


def default_mock_config(*, port_override: int | None = None) -> MockConfig:
    port = DEFAULT_MOCK_PORT
    if port_override is not None:
        port = _parse_port(port_override, field_name="--port")
    return MockConfig(port=port, routes=[])


def _parse_port(raw: object, *, field_name: str) -> int:
    if isinstance(raw, bool):
        raise ValidationError(f"{field_name} deve ser inteiro entre 1 e 65535")
    try:
        port = int(raw)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field_name} deve ser inteiro entre 1 e 65535") from error
    if port < 1 or port > 65535:
        raise ValidationError(f"{field_name} deve ser inteiro entre 1 e 65535")
    return port


def _parse_status(raw: object, *, field_name: str) -> int:
    if isinstance(raw, bool):
        raise ValidationError(f"{field_name} deve ser inteiro entre 100 e 599")
    try:
        status = int(raw)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field_name} deve ser inteiro entre 100 e 599") from error
    if status < 100 or status > 599:
        raise ValidationError(f"{field_name} deve ser inteiro entre 100 e 599")
    return status
