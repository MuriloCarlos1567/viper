from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml

from viper.naming import unique_service_name
from viper.paths import compose_file, project_root
from viper.ports import PortBinding


@dataclass(frozen=True)
class ComposeService:
    repo: str
    service: str
    port_bindings: list[PortBinding]


@dataclass(frozen=True)
class MockServiceSpec:
    service_name: str
    hostname: str
    host_port: int
    container_port: int
    build_context: Path


@dataclass(frozen=True)
class ServiceOverride:
    volumes: list[str]
    environment: dict[str, str]


def build_compose_document(
    root: Path,
    repos: list[str],
    resolved_port_bindings: dict[str, list[PortBinding]],
    mock_service: MockServiceSpec | None = None,
    service_overrides_by_repo: dict[str, ServiceOverride] | None = None,
) -> tuple[dict, dict[str, str]]:
    root = project_root(root)
    service_name_by_repo: dict[str, str] = {}
    used_service_names: set[str] = set()
    services: dict[str, dict] = {}
    service_overrides_by_repo = service_overrides_by_repo or {}

    for repo in sorted(repos):
        service_name = unique_service_name(repo, used_service_names)
        used_service_names.add(service_name)
        service_name_by_repo[repo] = service_name
        repo_bindings = resolved_port_bindings.get(repo, [])
        ports = [f"{binding.host_port}:{binding.container_port}" for binding in repo_bindings]
        repo_root = (root / "repos" / repo).resolve()
        repo_env = (repo_root / ".env").resolve()

        service: dict[str, object] = {
            "build": {"context": repo_root.as_posix()},
            "env_file": [repo_env.as_posix()],
            "restart": "unless-stopped",
            "labels": {"viper.repo": repo},
        }
        override = service_overrides_by_repo.get(repo)
        if override is not None:
            if override.volumes:
                service["volumes"] = override.volumes
            if override.environment:
                service["environment"] = dict(override.environment)
        if ports:
            service["ports"] = ports
        services[service_name] = service

    if mock_service is not None:
        health_cmd = (
            "import urllib.request,sys; "
            f"sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:{mock_service.container_port}/__health', timeout=2).status == 200 else 1)"
        )
        services[mock_service.service_name] = {
            "build": {"context": mock_service.build_context.resolve().as_posix()},
            "hostname": mock_service.hostname,
            "restart": "unless-stopped",
            "environment": {
                "VIPER_MOCK_PORT": str(mock_service.container_port),
            },
            "labels": {
                "viper.infrastructure": "mock",
            },
            "ports": [f"{mock_service.host_port}:{mock_service.container_port}"],
            "healthcheck": {
                "test": ["CMD", "python", "-c", health_cmd],
                "interval": "5s",
                "timeout": "2s",
                "retries": 10,
            },
        }

    document = {
        "services": services,
    }
    return document, service_name_by_repo


def write_compose_file(root: Path, compose_document: dict) -> Path:
    compose_path = compose_file(root)
    compose_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(compose_document, sort_keys=False)
    compose_path.write_text(yaml_text, encoding="utf-8")
    return compose_path
