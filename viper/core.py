from __future__ import annotations

from pathlib import Path
from typing import Callable

from viper.compose_generator import MockServiceSpec, build_compose_document, write_compose_file
from viper.env_parser import read_ports_from_env
from viper.exceptions import EnvParseError, PortConflictError, ValidationError
from viper.links import resolve_service_overrides
from viper.paths import DEFAULT_STACK_NAME, repos_dir, state_dir
from viper.ports import PortBinding, resolve_repo_port_bindings
from viper.runtime import ComposeRuntime
from viper.state import State


PromptFn = Callable[[str, int], int]


def ensure_workspace_dirs(root: Path) -> None:
    repos_dir(root).mkdir(parents=True, exist_ok=True)
    state_dir(root).mkdir(parents=True, exist_ok=True)


def repo_path(root: Path, repo: str) -> Path:
    return repos_dir(root) / repo


def validate_repo_structure(root: Path, repo: str) -> None:
    path = repo_path(root, repo)
    if not path.exists() or not path.is_dir():
        raise ValidationError(f"Repo não encontrado em repos/: {repo}")
    dockerfile = path / "Dockerfile"
    envfile = path / ".env"
    if not dockerfile.exists():
        raise ValidationError(f"Dockerfile ausente em repos/{repo}")
    if not envfile.exists():
        raise ValidationError(f".env ausente em repos/{repo}")
    try:
        read_ports_from_env(envfile)
    except EnvParseError as error:
        raise ValidationError(str(error)) from error


def resolve_stack_name(state: State, stack_name: str | None) -> str:
    return (stack_name or state.default_stack or DEFAULT_STACK_NAME).strip()


def generate_compose_assets(
    root: Path,
    state: State,
    *,
    interactive: bool,
    prompt_fn: PromptFn | None = None,
    mock_service: MockServiceSpec | None = None,
) -> tuple[Path, dict[str, str], dict[str, list[PortBinding]]]:
    resolved = resolve_all_port_bindings(root, state, interactive=interactive, prompt_fn=prompt_fn)
    if mock_service is not None:
        _ensure_mock_port_does_not_conflict(mock_service, resolved)
    service_overrides_by_repo = resolve_service_overrides(root, state)
    compose_doc, service_by_repo = build_compose_document(
        root,
        state.repos,
        resolved,
        mock_service=mock_service,
        service_overrides_by_repo=service_overrides_by_repo,
    )
    compose_path = write_compose_file(root, compose_doc)
    return compose_path, service_by_repo, resolved


def resolve_all_port_bindings(
    root: Path,
    state: State,
    *,
    interactive: bool,
    prompt_fn: PromptFn | None = None,
) -> dict[str, list[PortBinding]]:
    used_host_ports: dict[int, tuple[str, int]] = {}
    resolved: dict[str, list[PortBinding]] = {}
    new_overrides: dict[str, dict[str, int]] = {}

    for repo in sorted(state.repos):
        validate_repo_structure(root, repo)
        env_path = repo_path(root, repo) / ".env"
        requests = read_ports_from_env(env_path)
        bindings, overrides = resolve_repo_port_bindings(
            repo=repo,
            requests=requests,
            current_overrides=state.port_overrides.get(repo),
            used_host_ports=used_host_ports,
            interactive=interactive,
            prompt_fn=prompt_fn,
        )
        resolved[repo] = bindings
        if overrides:
            new_overrides[repo] = overrides

    state.port_overrides = new_overrides
    state.normalize()
    return resolved


def runtime_for(root: Path, state: State, stack_name: str) -> ComposeRuntime:
    compose_path, _, _ = generate_compose_assets(root, state, interactive=False)
    return ComposeRuntime(compose_path=compose_path, project_name=stack_name)


def _ensure_mock_port_does_not_conflict(
    mock_service: MockServiceSpec,
    resolved: dict[str, list[PortBinding]],
) -> None:
    for repo, bindings in resolved.items():
        for binding in bindings:
            if binding.host_port == mock_service.host_port:
                raise PortConflictError(
                    f"Porta de mock server em conflito ({mock_service.host_port}) com {repo}:{binding.container_port}. "
                    "Use --port para escolher outra porta."
                )
