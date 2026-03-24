from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
import tomli_w

from viper.paths import DEFAULT_STACK_NAME, state_dir, state_file


@dataclass
class State:
    default_stack: str = DEFAULT_STACK_NAME
    repos: list[str] = field(default_factory=list)
    port_overrides: dict[str, dict[str, int]] = field(default_factory=dict)
    library_links: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def normalize(self) -> None:
        self.repos = sorted(set(self.repos))
        normalized: dict[str, dict[str, int]] = {}
        for repo, mapping in self.port_overrides.items():
            if not isinstance(mapping, dict):
                continue
            normalized[repo] = {
                str(container): int(host)
                for container, host in mapping.items()
                if str(container).isdigit() and isinstance(host, int | str)
            }
        self.port_overrides = normalized
        self.library_links = _normalize_library_links(self.library_links)


def empty_state() -> State:
    return State()


def load_state(root: Path | None = None) -> State:
    path = state_file(root)
    if not path.exists():
        return empty_state()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    state = State(
        default_stack=str(data.get("default_stack", DEFAULT_STACK_NAME)),
        repos=[str(repo) for repo in data.get("repos", [])],
        port_overrides={
            str(repo): {
                str(container_port): int(host_port)
                for container_port, host_port in mapping.items()
            }
            for repo, mapping in data.get("port_overrides", {}).items()
            if isinstance(mapping, dict)
        },
        library_links={
            str(api_repo): [
                {
                    "lib_repo": str(item.get("lib_repo", "")),
                    "subpath": str(item.get("subpath", "src")),
                }
                for item in links
                if isinstance(item, dict)
            ]
            for api_repo, links in data.get("library_links", {}).items()
            if isinstance(links, list)
        },
    )
    state.normalize()
    return state


def save_state(state: State, root: Path | None = None) -> None:
    state.normalize()
    directory = state_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "default_stack": state.default_stack,
        "repos": state.repos,
        "port_overrides": state.port_overrides,
        "library_links": state.library_links,
    }
    state_file(root).write_text(tomli_w.dumps(data), encoding="utf-8")


def _normalize_library_links(raw: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    normalized: dict[str, list[dict[str, str]]] = {}
    if not isinstance(raw, dict):
        return normalized

    for api_repo, links in raw.items():
        api_key = str(api_repo).strip()
        if not api_key or not isinstance(links, list):
            continue

        seen: set[tuple[str, str]] = set()
        cleaned: list[dict[str, str]] = []
        for item in links:
            if not isinstance(item, dict):
                continue
            lib_repo = str(item.get("lib_repo", "")).strip()
            subpath = _normalize_subpath(str(item.get("subpath", "src")))
            if not lib_repo:
                continue
            key = (lib_repo, subpath)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"lib_repo": lib_repo, "subpath": subpath})

        if cleaned:
            cleaned.sort(key=lambda link: (link["lib_repo"], link["subpath"]))
            normalized[api_key] = cleaned

    return dict(sorted(normalized.items()))


def _normalize_subpath(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    if not value:
        return "src"
    if value in (".", "./"):
        return "."
    value = value.strip("/")
    parts = [part for part in value.split("/") if part and part != "."]
    if not parts:
        return "."
    return "/".join(parts)

