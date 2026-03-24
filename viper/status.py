from __future__ import annotations

from dataclasses import dataclass
import socket

from viper.ports import PortBinding


@dataclass(frozen=True)
class RepoStatusRow:
    repo: str
    service: str
    container: str
    state: str
    health: str
    ports: str


def probe_host_port(host_port: int, timeout_seconds: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_seconds)
        return sock.connect_ex(("127.0.0.1", host_port)) == 0


def health_with_fallback(
    compose_entry: dict,
    repo_bindings: list[PortBinding],
) -> str:
    health = str(compose_entry.get("Health", "")).strip()
    if health:
        return health

    state = str(compose_entry.get("State", "")).strip().lower()
    if state != "running":
        return "-"
    if not repo_bindings:
        return "running"

    all_open = all(probe_host_port(binding.host_port) for binding in repo_bindings)
    return "healthy" if all_open else "unhealthy"
