from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from viper.compose_generator import ServiceOverride
from viper.env_parser import parse_env_file
from viper.exceptions import ValidationError
from viper.paths import repos_dir
from viper.state import State


DEFAULT_LINK_SUBPATH = "src"


@dataclass(frozen=True)
class LibraryLink:
    lib_repo: str
    subpath: str


def validate_link_candidate(
    root: Path,
    state: State,
    *,
    api_repo: str,
    lib_repo: str,
    subpath: str,
) -> LibraryLink:
    api_repo = api_repo.strip()
    lib_repo = lib_repo.strip()
    if not api_repo:
        raise ValidationError("Parametro --api obrigatorio.")
    if not lib_repo:
        raise ValidationError("Parametro --lib obrigatorio.")
    if api_repo not in state.repos:
        raise ValidationError(f"API repo nao registrado: {api_repo}")

    normalized_subpath = normalize_link_subpath(subpath)
    _validate_link_target_exists(root, lib_repo, normalized_subpath)
    return LibraryLink(lib_repo=lib_repo, subpath=normalized_subpath)


def resolve_service_overrides(root: Path, state: State) -> dict[str, ServiceOverride]:
    overrides: dict[str, ServiceOverride] = {}
    base_repos = repos_dir(root)

    for api_repo in sorted(state.library_links):
        if api_repo not in state.repos:
            raise ValidationError(f"Link invalido: API repo nao registrado no estado: {api_repo}")

        links = state.library_links.get(api_repo, [])
        if not links:
            continue

        mount_paths: list[str] = []
        volumes: list[str] = []
        for link in links:
            lib_repo = str(link.get("lib_repo", "")).strip()
            subpath = normalize_link_subpath(str(link.get("subpath", DEFAULT_LINK_SUBPATH)))
            if not lib_repo:
                continue
            host_path = _validate_link_target_exists(root, lib_repo, subpath)
            container_path = _container_mount_path(lib_repo, subpath)
            volumes.append(f"{host_path.as_posix()}:{container_path}:ro")
            mount_paths.append(container_path)

        if not mount_paths:
            continue

        existing_pythonpath = _read_existing_pythonpath(base_repos / api_repo / ".env")
        pythonpath_parts = mount_paths + ([existing_pythonpath] if existing_pythonpath else [])
        final_pythonpath = ":".join(pythonpath_parts)
        overrides[api_repo] = ServiceOverride(
            volumes=volumes,
            environment={"PYTHONPATH": final_pythonpath},
        )

    return overrides


def normalize_link_subpath(subpath: str) -> str:
    raw = subpath.strip().replace("\\", "/")
    if not raw:
        raw = DEFAULT_LINK_SUBPATH
    if raw in (".", "./"):
        return "."
    if raw.startswith("/"):
        raise ValidationError(f"Subpath invalido (absoluto): {subpath}")

    pieces = [piece for piece in raw.split("/") if piece and piece != "."]
    if not pieces:
        return "."
    if any(piece == ".." for piece in pieces):
        raise ValidationError(f"Subpath invalido (nao pode conter '..'): {subpath}")
    return "/".join(pieces)


def _validate_link_target_exists(root: Path, lib_repo: str, subpath: str) -> Path:
    lib_root = repos_dir(root) / lib_repo
    if not lib_root.exists() or not lib_root.is_dir():
        raise ValidationError(f"Lib repo nao encontrado em repos/: {lib_repo}")

    target = lib_root if subpath == "." else (lib_root / subpath)
    if not target.exists() or not target.is_dir():
        raise ValidationError(
            f"Subpath de link nao encontrado para lib {lib_repo}: {subpath}. "
            "Informe um subpath valido com --subpath."
        )
    return target.resolve()


def _container_mount_path(lib_repo: str, subpath: str) -> str:
    safe_repo = re.sub(r"[^a-zA-Z0-9_.-]+", "-", lib_repo).strip("-") or "lib"
    safe_subpath = "root" if subpath == "." else subpath.replace("/", "__")
    return f"/opt/viper-links/{safe_repo}/{safe_subpath}"


def _read_existing_pythonpath(env_path: Path) -> str:
    try:
        data = parse_env_file(env_path)
    except Exception:
        return ""
    return str(data.get("PYTHONPATH", "")).strip()
