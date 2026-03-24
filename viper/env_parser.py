from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from viper.exceptions import EnvParseError


_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


@dataclass(frozen=True)
class PortRequest:
    container_port: int
    suggested_host_port: int


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        raise EnvParseError(f".env não encontrado: {path}")

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = _LINE_RE.match(raw_line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        data[key] = _strip_inline_comment(value.strip())
    return data


def read_ports_from_env(path: Path) -> list[PortRequest]:
    env_data = parse_env_file(path)
    if "PORTS" in env_data and env_data["PORTS"].strip():
        ports = _parse_ports_value(env_data["PORTS"])
    elif "PORT" in env_data and env_data["PORT"].strip():
        port = _parse_port(env_data["PORT"], key_name="PORT")
        ports = [(port, port)]
    else:
        raise EnvParseError(f".env sem PORT/PORTS: {path}")

    container_seen: set[int] = set()
    requests: list[PortRequest] = []
    for host_port, container_port in ports:
        if container_port in container_seen:
            raise EnvParseError(f"Porta duplicada no .env ({container_port}) em {path}")
        container_seen.add(container_port)
        requests.append(
            PortRequest(
                container_port=container_port,
                suggested_host_port=host_port,
            )
        )
    return requests


def _strip_inline_comment(value: str) -> str:
    if not value:
        return value
    if value[0] in ('"', "'") and value[-1:] == value[0]:
        return value[1:-1]

    hash_index = value.find("#")
    if hash_index >= 0:
        return value[:hash_index].strip()
    return value


def _parse_ports_value(value: str) -> list[tuple[int, int]]:
    tokens = [token.strip() for token in value.split(",") if token.strip()]
    if not tokens:
        raise EnvParseError("PORTS está vazio")

    bindings: list[tuple[int, int]] = []
    for token in tokens:
        if ":" in token:
            left, right = [part.strip() for part in token.split(":", 1)]
            host_port = _parse_port(left, key_name="PORTS(host)")
            container_port = _parse_port(right, key_name="PORTS(container)")
        else:
            container_port = _parse_port(token, key_name="PORTS")
            host_port = container_port
        bindings.append((host_port, container_port))
    return bindings


def _parse_port(raw: str, key_name: str) -> int:
    if not raw.strip().isdigit():
        raise EnvParseError(f"Porta inválida em {key_name}: {raw!r}")
    port = int(raw.strip())
    if port < 1 or port > 65535:
        raise EnvParseError(f"Porta fora do intervalo em {key_name}: {port}")
    return port
