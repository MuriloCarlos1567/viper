from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from viper.env_parser import PortRequest
from viper.exceptions import PortConflictError


PromptFn = Callable[[str, int], int]


@dataclass(frozen=True)
class PortBinding:
    repo: str
    host_port: int
    container_port: int


def resolve_repo_port_bindings(
    repo: str,
    requests: list[PortRequest],
    current_overrides: dict[str, int] | None,
    used_host_ports: dict[int, tuple[str, int]],
    interactive: bool,
    prompt_fn: PromptFn | None = None,
) -> tuple[list[PortBinding], dict[str, int]]:
    overrides = dict(current_overrides or {})
    bindings: list[PortBinding] = []

    for request in requests:
        container_key = str(request.container_port)
        desired_host_port = overrides.get(container_key, request.suggested_host_port)
        chosen = _ensure_available_host_port(
            repo=repo,
            container_port=request.container_port,
            desired_host_port=desired_host_port,
            used_host_ports=used_host_ports,
            interactive=interactive,
            prompt_fn=prompt_fn,
        )
        if chosen != request.suggested_host_port:
            overrides[container_key] = chosen
        elif container_key in overrides:
            del overrides[container_key]

        used_host_ports[chosen] = (repo, request.container_port)
        bindings.append(
            PortBinding(
                repo=repo,
                host_port=chosen,
                container_port=request.container_port,
            )
        )

    return bindings, overrides


def next_free_port(start_port: int, used_host_ports: dict[int, tuple[str, int]]) -> int:
    candidate = max(1, start_port)
    while candidate in used_host_ports:
        candidate += 1
    return candidate


def _ensure_available_host_port(
    repo: str,
    container_port: int,
    desired_host_port: int,
    used_host_ports: dict[int, tuple[str, int]],
    interactive: bool,
    prompt_fn: PromptFn | None,
) -> int:
    owner = used_host_ports.get(desired_host_port)
    if owner is None or owner == (repo, container_port):
        return desired_host_port

    if not interactive:
        raise PortConflictError(
            f"Conflito de porta: host:{desired_host_port} já usado por {owner[0]}:{owner[1]}"
        )

    suggested = next_free_port(desired_host_port + 1, used_host_ports)
    if prompt_fn is None:
        return suggested

    prompt = (
        f"Conflito de porta para {repo} (container:{container_port} -> host:{desired_host_port}). "
        f"Escolha uma porta host livre"
    )
    chosen = prompt_fn(prompt, suggested)
    while chosen in used_host_ports:
        suggested = next_free_port(chosen + 1, used_host_ports)
        chosen = prompt_fn(
            f"Porta {chosen} já está em uso. Escolha outra porta host livre",
            suggested,
        )
    return chosen
