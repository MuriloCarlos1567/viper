from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import time
from typing import Iterable

import typer
from rich.table import Table

from viper.core import (
    ensure_workspace_dirs,
    generate_compose_assets,
    repo_path,
    resolve_stack_name,
    validate_repo_structure,
)
from viper.exceptions import ViperError, PortConflictError, ValidationError
from viper.links import DEFAULT_LINK_SUBPATH, normalize_link_subpath, validate_link_candidate
from viper.mock_config import MockConfig, default_mock_config, load_mock_config
from viper.mock_runtime import MOCK_HOSTNAME, prepare_mock_service
from viper.paths import mock_config_file, repos_dir, state_dir, state_file
from viper.runtime import ComposeRuntime
from viper.state import State, load_state, save_state
from viper.status import RepoStatusRow, health_with_fallback
from viper.ui import (
    DoctorCheck,
    console,
    estado_legivel,
    print_doctor_table,
    print_error,
    print_ports_json,
    print_ports_table,
    saude_legivel,
    print_status_table,
    print_success,
    print_warning,
    stream_colored_logs,
)


app = typer.Typer(help="Viper: orquestrador local de multiplos repositorios com Docker Compose.")
mock_app = typer.Typer(help="Comandos de mock server para APIs locais.")
app.add_typer(mock_app, name="mock")
link_app = typer.Typer(help="Vinculos de bibliotecas locais para APIs Python.")
app.add_typer(link_app, name="link")


def _cwd() -> Path:
    return Path.cwd().resolve()


def _prompt_port(message: str, default: int) -> int:
    return typer.prompt(message, type=int, default=default)


def _generate_compose_or_exit(
    root: Path,
    state: State,
    *,
    interactive: bool,
) -> tuple[Path, dict[str, str], dict[str, list]]:
    try:
        return generate_compose_assets(root, state, interactive=interactive, prompt_fn=_prompt_port)
    except PortConflictError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error


def _runtime(compose_path: Path, stack_name: str) -> ComposeRuntime:
    return ComposeRuntime(compose_path=compose_path, project_name=stack_name)


def _resolve_input_path(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else (root / value).resolve()


def _load_mock_config_or_exit(
    root: Path,
    config: Path | None,
    *,
    port_override: int | None = None,
    require_existing: bool = True,
) -> tuple[Path, MockConfig]:
    config_path = _resolve_input_path(root, config or mock_config_file(root))
    try:
        if require_existing:
            return config_path, load_mock_config(config_path, port_override=port_override)
        if config_path.exists():
            return config_path, load_mock_config(config_path, port_override=port_override)
        return config_path, default_mock_config(port_override=port_override)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error


def _generate_compose_with_mock_or_exit(
    root: Path,
    state: State,
    mock_config: MockConfig,
) -> tuple[Path, str]:
    try:
        mock_service = prepare_mock_service(root, mock_config)
        compose_path, _, _ = generate_compose_assets(
            root,
            state,
            interactive=False,
            mock_service=mock_service,
        )
        return compose_path, mock_service.service_name
    except PortConflictError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error


def _restart_api_if_running(
    root: Path,
    state: State,
    *,
    api_repo: str,
    stack_name: str,
) -> bool:
    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
    service_name = service_by_repo.get(api_repo)
    if service_name is None:
        return False

    runtime = _runtime(compose_path, stack_name)
    entries = runtime.ps_json()
    entry = next((item for item in entries if str(item.get("Service", "")) == service_name), None)
    if entry is None:
        return False
    if str(entry.get("State", "")).lower() != "running":
        return False

    # `restart` does not re-read compose service env/volumes.
    # Recreate the service so link changes (PYTHONPATH + mounts) take effect.
    runtime.run(["up", "-d", "--build", "--force-recreate", service_name])
    return True


def _get_links_for_api(state: State, api_repo: str) -> list[dict[str, str]]:
    links = state.library_links.get(api_repo)
    if links is None:
        links = []
        state.library_links[api_repo] = links
    return links


def _link_exists(state: State, api_repo: str, lib_repo: str, subpath: str) -> bool:
    links = state.library_links.get(api_repo, [])
    return any(item.get("lib_repo") == lib_repo and item.get("subpath") == subpath for item in links)


def _ensure_registered(state: State, repo: str) -> None:
    if repo not in state.repos:
        raise ValidationError(f"Repo não registrado: {repo}")


def _ensure_repos_registered(state: State) -> None:
    if not state.repos:
        raise ValidationError("Nenhum repo registrado. Use 'viper add <repo>' ou 'viper sync'.")


def _rows_for_ports(
    state: State,
    service_by_repo: dict[str, str],
    resolved: dict[str, list],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for repo in sorted(resolved):
        service = service_by_repo.get(repo, "-")
        overrides = state.port_overrides.get(repo, {})
        for binding in resolved[repo]:
            key = str(binding.container_port)
            source = "override" if overrides.get(key) == binding.host_port else ".env"
            rows.append(
                {
                    "repo": repo,
                    "service": service,
                    "host_port": str(binding.host_port),
                    "container_port": str(binding.container_port),
                    "source": source,
                }
            )
    return rows


def _status_rows(
    state: State,
    service_by_repo: dict[str, str],
    resolved: dict[str, list],
    ps_entries: list[dict],
) -> list[RepoStatusRow]:
    entry_by_service = {str(entry.get("Service", "")): entry for entry in ps_entries}
    rows: list[RepoStatusRow] = []

    for repo in sorted(state.repos):
        service = service_by_repo.get(repo, "-")
        entry = entry_by_service.get(service)
        ports_label = ", ".join(
            f"{binding.host_port}:{binding.container_port}" for binding in resolved.get(repo, [])
        ) or "-"

        if entry is None:
            rows.append(
                RepoStatusRow(
                    repo=repo,
                    service=service,
                    container="-",
                    state="not-created",
                    health="-",
                    ports=ports_label,
                )
            )
            continue

        rows.append(
            RepoStatusRow(
                repo=repo,
                service=service,
                container=str(entry.get("Name", "-")),
                state=str(entry.get("State", "unknown")),
                health=health_with_fallback(entry, resolved.get(repo, [])),
                ports=ports_label,
            )
        )
    return rows


def _render_status_table(rows: Iterable[RepoStatusRow]) -> Table:
    table = Table(title="Status dos Repositórios", header_style="bold cyan")
    table.add_column("Repositorio", style="bold")
    table.add_column("Servico")
    table.add_column("Container")
    table.add_column("Estado")
    table.add_column("Saude")
    table.add_column("Portas")
    for row in rows:
        table.add_row(
            row.repo,
            row.service,
            row.container,
            estado_legivel(row.state),
            saude_legivel(row.health),
            row.ports,
        )
    return table


@app.command()
def init(
    name: str = typer.Option("viper", "--name", help="Nome padrão da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    ensure_workspace_dirs(root)
    state.default_stack = name
    save_state(state, root)
    print_success(f"Area de trabalho inicializada em {root}")
    print_success(f"Stack padrão: {name}")


@app.command()
def add(repo: str = typer.Argument(..., help="Nome da pasta já existente em repos/<repo>.")) -> None:
    root = _cwd()
    state = load_state(root)
    ensure_workspace_dirs(root)

    try:
        validate_repo_structure(root, repo)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    if repo in state.repos:
        print_warning(f"Repo já registrado: {repo}")
        raise typer.Exit(code=0)

    state.repos.append(repo)
    state.normalize()
    compose_path, service_by_repo, resolved = _generate_compose_or_exit(root, state, interactive=True)
    save_state(state, root)

    print_success(f"Repo registrado: {repo}")
    print_success(f"Compose atualizado: {compose_path}")
    print_ports_table(_rows_for_ports(state, service_by_repo, resolved))


@app.command()
def remove(
    repo: str = typer.Argument(..., help="Repo a remover do registro e da stack."),
    keep_files: bool = typer.Option(True, "--keep-files/--delete-files", help="Manter ou remover pasta em repos/."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)

    try:
        _ensure_registered(state, repo)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    stack = resolve_stack_name(state, name)
    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
    runtime = _runtime(compose_path, stack)
    service = service_by_repo[repo]
    runtime.stop_remove_service(service)

    state.repos = [item for item in state.repos if item != repo]
    state.port_overrides.pop(repo, None)
    state.normalize()
    _generate_compose_or_exit(root, state, interactive=False)
    save_state(state, root)

    if not keep_files:
        shutil.rmtree(repo_path(root, repo), ignore_errors=True)
    print_success(f"Repo removido: {repo}")


@app.command()
def up(
    repo: str | None = typer.Argument(None, help="Repo específico para subir. Se omitido, sobe todos."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    try:
        _ensure_repos_registered(state)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    if repo is not None and repo not in state.repos:
        print_error(f"Repo não registrado: {repo}")
        raise typer.Exit(code=1)

    stack = resolve_stack_name(state, name)
    with console.status("[bold cyan]Gerando compose e resolvendo portas..."):
        compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=True)
        save_state(state, root)

    runtime = _runtime(compose_path, stack)
    services = [service_by_repo[repo]] if repo else None
    with console.status("[bold cyan]Subindo serviços..."):
        runtime.up(services=services)
    print_success("Serviços iniciados")


@app.command()
def down(
    repo: str | None = typer.Argument(None, help="Repo específico para derrubar. Se omitido, derruba toda stack."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
    runtime = _runtime(compose_path, stack)

    if repo:
        if repo not in state.repos:
            print_error(f"Repo não registrado: {repo}")
            raise typer.Exit(code=1)
        runtime.stop_remove_service(service_by_repo[repo])
        print_success(f"Serviço parado/removido: {repo}")
        return

    runtime.down()
    print_success("Stack derrubada")


@app.command()
def restart(
    repo: str | None = typer.Argument(None, help="Repo específico para reiniciar."),
    all: bool = typer.Option(False, "--all", help="Reiniciar todos os serviços."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)

    if not all and repo is None:
        print_error("Informe um repo ou use --all.")
        raise typer.Exit(code=1)
    if all and repo is not None:
        print_error("Use repo OU --all, não ambos.")
        raise typer.Exit(code=1)

    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
    runtime = _runtime(compose_path, stack)

    if all:
        runtime.restart()
        print_success("Todos os serviços foram reiniciados")
        return

    if repo not in state.repos:
        print_error(f"Repo não registrado: {repo}")
        raise typer.Exit(code=1)
    runtime.restart([service_by_repo[repo]])
    print_success(f"Serviço reiniciado: {repo}")


@app.command()
def update(
    repo: str = typer.Argument(..., help="Repo a atualizar com estratégia remove+add+up."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    ensure_workspace_dirs(root)

    if repo in state.repos:
        compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
        runtime = _runtime(compose_path, stack)
        runtime.stop_remove_service(service_by_repo[repo])
        state.repos = [item for item in state.repos if item != repo]
        state.port_overrides.pop(repo, None)

    try:
        validate_repo_structure(root, repo)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    state.repos.append(repo)
    state.normalize()
    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=True)
    save_state(state, root)

    runtime = _runtime(compose_path, stack)
    runtime.up([service_by_repo[repo]])
    print_success(f"Repo atualizado e re-subido: {repo}")


@app.command()
def ports(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
    json: bool = typer.Option(False, "--json", help="Emitir saída JSON."),
) -> None:
    root = _cwd()
    state = load_state(root)
    if not state.repos:
        print_warning("Nenhum repo registrado.")
        raise typer.Exit(code=0)

    _ = resolve_stack_name(state, name)
    compose_path, service_by_repo, resolved = _generate_compose_or_exit(root, state, interactive=False)
    save_state(state, root)
    rows = _rows_for_ports(state, service_by_repo, resolved)

    if json:
        print_ports_json(rows)
    else:
        print_ports_table(rows)
    print_success(f"Compose atual: {compose_path}")


@app.command()
def status(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
    watch: bool = typer.Option(False, "--watch", help="Atualiza tabela continuamente."),
    interval: int = typer.Option(2, "--interval", help="Intervalo em segundos para --watch."),
) -> None:
    root = _cwd()
    state = load_state(root)
    if not state.repos:
        print_warning("Nenhum repo registrado.")
        raise typer.Exit(code=0)

    stack = resolve_stack_name(state, name)
    compose_path, service_by_repo, resolved = _generate_compose_or_exit(root, state, interactive=False)
    runtime = _runtime(compose_path, stack)

    if not watch:
        rows = _status_rows(state, service_by_repo, resolved, runtime.ps_json())
        print_status_table(rows)
        raise typer.Exit(code=0)

    try:
        while True:
            rows = _status_rows(state, service_by_repo, resolved, runtime.ps_json())
            console.clear()
            console.print(_render_status_table(rows))
            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        print_warning("Monitoramento interrompido.")


@app.command()
def logs(
    repo: str | None = typer.Argument(None, help="Repo específico. Sem repo, usa --all."),
    all: bool = typer.Option(False, "--all", help="Mostrar logs de todos os serviços."),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)

    if repo and all:
        print_error("Use repo OU --all.")
        raise typer.Exit(code=1)
    if not repo and not all:
        all = True

    compose_path, service_by_repo, _ = _generate_compose_or_exit(root, state, interactive=False)
    runtime = _runtime(compose_path, stack)
    services = None
    if repo:
        if repo not in state.repos:
            print_error(f"Repo não registrado: {repo}")
            raise typer.Exit(code=1)
        services = [service_by_repo[repo]]

    process = runtime.logs_follow(services)
    try:
        if process.stdout is None:
            print_warning("Sem stream de logs.")
            return
        stream_colored_logs(process.stdout)
    except KeyboardInterrupt:
        print_warning("Logs interrompidos.")
    finally:
        process.terminate()


@app.command()
def sync() -> None:
    root = _cwd()
    state = load_state(root)
    ensure_workspace_dirs(root)

    repo_dirs = sorted(
        entry.name
        for entry in repos_dir(root).iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )
    new_repos = [repo for repo in repo_dirs if repo not in state.repos]
    if not new_repos:
        print_success("Nenhum novo repo para registrar.")
        return

    added: list[str] = []
    for repo in new_repos:
        register = typer.confirm(f"Registrar repo detectado: {repo}?", default=True)
        if not register:
            continue
        try:
            validate_repo_structure(root, repo)
        except ValidationError as error:
            print_warning(str(error))
            continue
        state.repos.append(repo)
        added.append(repo)

    if not added:
        print_warning("Nenhum repo foi registrado.")
        return

    state.normalize()
    _generate_compose_or_exit(root, state, interactive=True)
    save_state(state, root)
    print_success(f"Repos registrados: {', '.join(added)}")


@link_app.command("add")
def link_add(
    api: str = typer.Option(..., "--api", help="Repo da API registrado no Viper."),
    lib: str = typer.Option(..., "--lib", help="Repo da biblioteca dentro de repos/."),
    subpath: str = typer.Option(
        DEFAULT_LINK_SUBPATH,
        "--subpath",
        help="Subpath da lib a montar (default: src). Use '.' para raiz.",
    ),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose (para restart automatico)."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)

    try:
        link = validate_link_candidate(
            root,
            state,
            api_repo=api,
            lib_repo=lib,
            subpath=subpath,
        )
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    if _link_exists(state, api, link.lib_repo, link.subpath):
        print_warning(f"Link ja existe: {api} -> {link.lib_repo}:{link.subpath}")
        raise typer.Exit(code=0)

    links = _get_links_for_api(state, api)
    links.append({"lib_repo": link.lib_repo, "subpath": link.subpath})
    state.normalize()
    save_state(state, root)

    restarted = _restart_api_if_running(root, state, api_repo=api, stack_name=stack)
    print_success(f"Link adicionado: {api} -> {link.lib_repo}:{link.subpath}")
    if restarted:
        print_success(f"API reiniciada para aplicar link: {api}")
    else:
        print_warning(f"API {api} nao estava rodando. O vinculo sera aplicado no proximo 'viper up'.")


@link_app.command("list")
def link_list(
    api: str | None = typer.Option(None, "--api", help="Filtrar links de uma API especifica."),
    json_output: bool = typer.Option(False, "--json", help="Emitir saida em JSON."),
) -> None:
    root = _cwd()
    state = load_state(root)

    rows: list[dict[str, str]] = []
    apis = [api] if api else sorted(state.library_links)
    for api_repo in apis:
        for link in state.library_links.get(api_repo, []):
            rows.append(
                {
                    "api_repo": api_repo,
                    "lib_repo": str(link.get("lib_repo", "")),
                    "subpath": str(link.get("subpath", "")),
                }
            )

    if json_output:
        console.print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print_warning("Nenhum link configurado.")
        return

    table = Table(title="Links de Bibliotecas", header_style="bold cyan")
    table.add_column("API Repo", style="bold")
    table.add_column("Lib Repo")
    table.add_column("Subpath")
    for row in rows:
        table.add_row(row["api_repo"], row["lib_repo"], row["subpath"])
    console.print(table)


@link_app.command("remove")
def link_remove(
    api: str = typer.Option(..., "--api", help="Repo da API registrado no Viper."),
    lib: str = typer.Option(..., "--lib", help="Repo da biblioteca vinculado."),
    subpath: str = typer.Option(
        DEFAULT_LINK_SUBPATH,
        "--subpath",
        help="Subcaminho usado no vinculo (padrao: src).",
    ),
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose (para restart automatico)."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)

    if api not in state.repos:
        print_error(f"API repo nao registrado: {api}")
        raise typer.Exit(code=1)

    try:
        normalized_subpath = normalize_link_subpath(subpath)
    except ValidationError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    links = state.library_links.get(api, [])
    if not links:
        print_error(f"Nenhum link encontrado para API: {api}")
        raise typer.Exit(code=1)

    filtered = [
        item
        for item in links
        if not (
            str(item.get("lib_repo", "")).strip() == lib.strip()
            and str(item.get("subpath", "")).strip() == normalized_subpath
        )
    ]
    if len(filtered) == len(links):
        print_error(f"Link nao encontrado: {api} -> {lib}:{normalized_subpath}")
        raise typer.Exit(code=1)

    if filtered:
        state.library_links[api] = filtered
    else:
        state.library_links.pop(api, None)
    state.normalize()
    save_state(state, root)

    restarted = _restart_api_if_running(root, state, api_repo=api, stack_name=stack)
    print_success(f"Link removido: {api} -> {lib}:{normalized_subpath}")
    if restarted:
        print_success(f"API reiniciada para aplicar remocao de link: {api}")
    else:
        print_warning(f"API {api} nao estava rodando. A remocao sera aplicada no proximo 'viper up'.")


@mock_app.command("validate")
def mock_validate(
    config: Path = typer.Option(Path("viper.mock.yaml"), "--config", help="Arquivo YAML de mock."),
) -> None:
    root = _cwd()
    config_path, mock_config = _load_mock_config_or_exit(root, config, require_existing=True)
    print_success(f"Configuracao valida: {config_path}")
    print_success(f"Porta mock: {mock_config.port} | Rotas: {len(mock_config.routes)}")


@mock_app.command("up")
def mock_up(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
    port: int | None = typer.Option(None, "--port", help="Sobrescreve a porta do mock server."),
    config: Path = typer.Option(Path("viper.mock.yaml"), "--config", help="Arquivo YAML de mock."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    config_path, mock_config = _load_mock_config_or_exit(
        root,
        config,
        port_override=port,
        require_existing=True,
    )

    with console.status("[bold cyan]Preparando mock server..."):
        compose_path, service_name = _generate_compose_with_mock_or_exit(root, state, mock_config)
        save_state(state, root)

    runtime = _runtime(compose_path, stack)
    with console.status("[bold cyan]Subindo mock server..."):
        runtime.up([service_name])
    print_success(f"Mock server iniciado: http://localhost:{mock_config.port}")
    print_success(f"DNS interno no Docker: http://{MOCK_HOSTNAME}:{mock_config.port}")
    print_success(f"Config usada: {config_path}")


@mock_app.command("down")
def mock_down(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    _, mock_config = _load_mock_config_or_exit(root, None, require_existing=False)
    compose_path, service_name = _generate_compose_with_mock_or_exit(root, state, mock_config)
    runtime = _runtime(compose_path, stack)
    runtime.stop_remove_service(service_name)
    print_success("Mock server parado/removido")


@mock_app.command("status")
def mock_status(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    _, mock_config = _load_mock_config_or_exit(root, None, require_existing=False)
    compose_path, service_name = _generate_compose_with_mock_or_exit(root, state, mock_config)
    runtime = _runtime(compose_path, stack)

    entries = runtime.ps_json()
    entry = next((item for item in entries if str(item.get("Service", "")) == service_name), None)

    if entry is None:
        row = RepoStatusRow(
            repo="mock",
            service=service_name,
            container="-",
            state="not-created",
            health="-",
            ports=f"{mock_config.port}:{mock_config.port}",
        )
    else:
        publishers = entry.get("Publishers")
        if isinstance(publishers, list) and publishers:
            ports_label = ", ".join(
                f"{publisher.get('PublishedPort')}:{publisher.get('TargetPort')}"
                for publisher in publishers
                if isinstance(publisher, dict)
            ) or f"{mock_config.port}:{mock_config.port}"
        else:
            ports_label = str(entry.get("Ports", f"{mock_config.port}:{mock_config.port}"))

        health_value = str(entry.get("Health", "")).strip()
        state_value = str(entry.get("State", "unknown"))
        row = RepoStatusRow(
            repo="mock",
            service=service_name,
            container=str(entry.get("Name", "-")),
            state=state_value,
            health=health_value or ("running" if state_value.lower() == "running" else "-"),
            ports=ports_label,
        )

    print_status_table([row], title="Status do mock server")


@mock_app.command("logs")
def mock_logs(
    name: str | None = typer.Option(None, "--name", help="Nome da stack Compose."),
) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    _, mock_config = _load_mock_config_or_exit(root, None, require_existing=False)
    compose_path, service_name = _generate_compose_with_mock_or_exit(root, state, mock_config)
    runtime = _runtime(compose_path, stack)

    process = runtime.logs_follow([service_name])
    try:
        if process.stdout is None:
            print_warning("Sem stream de logs.")
            return
        stream_colored_logs(process.stdout)
    except KeyboardInterrupt:
        print_warning("Logs interrompidos.")
    finally:
        process.terminate()


@app.command()
def doctor(name: str | None = typer.Option(None, "--name", help="Nome da stack Compose.")) -> None:
    root = _cwd()
    state = load_state(root)
    stack = resolve_stack_name(state, name)
    checks: list[DoctorCheck] = []

    def run_check(title: str, command: list[str]) -> None:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if completed.returncode == 0:
            details = completed.stdout.strip() or completed.stderr.strip() or "ok"
            checks.append(DoctorCheck(title, "APROVADO", details))
        else:
            details = completed.stderr.strip() or completed.stdout.strip() or "erro"
            checks.append(DoctorCheck(title, "FALHA", details))

    run_check("docker", ["docker", "--version"])
    run_check("docker compose", ["docker", "compose", "version"])

    checks.append(
        DoctorCheck(
            "repos/ existe",
            "APROVADO" if repos_dir(root).exists() else "AVISO",
            str(repos_dir(root)),
        )
    )
    checks.append(
        DoctorCheck(
            "diretorio de estado existe",
            "APROVADO" if state_dir(root).exists() else "AVISO",
            str(state_dir(root)),
        )
    )
    checks.append(
        DoctorCheck(
            "state.toml",
            "APROVADO" if state_file(root).exists() else "AVISO",
            str(state_file(root)),
        )
    )

    for repo in state.repos:
        try:
            validate_repo_structure(root, repo)
            checks.append(DoctorCheck(f"repo:{repo}", "APROVADO", "Dockerfile/.env valido"))
        except ValidationError as error:
            checks.append(DoctorCheck(f"repo:{repo}", "FALHA", str(error)))

    for api_repo, links in state.library_links.items():
        if not links:
            continue
        for link in links:
            lib_repo = str(link.get("lib_repo", "")).strip()
            subpath = str(link.get("subpath", DEFAULT_LINK_SUBPATH)).strip()
            try:
                validate_link_candidate(
                    root,
                    state,
                    api_repo=api_repo,
                    lib_repo=lib_repo,
                    subpath=subpath,
                )
                checks.append(DoctorCheck(f"link:{api_repo}->{lib_repo}", "APROVADO", f"subcaminho={subpath}"))
            except ValidationError as error:
                checks.append(DoctorCheck(f"link:{api_repo}->{lib_repo}", "FALHA", str(error)))

    if state.repos:
        try:
            compose_path, _, _ = _generate_compose_or_exit(root, state, interactive=False)
            runtime = _runtime(compose_path, stack)
            checks.append(
                DoctorCheck(
                    "configuracao do compose",
                    "APROVADO" if runtime.config_validate() else "FALHA",
                    str(compose_path),
                )
            )
        except (ViperError, ValidationError) as error:
            checks.append(DoctorCheck("configuracao do compose", "FALHA", str(error)))

    print_doctor_table(checks)
    has_fail = any(check.status == "FALHA" for check in checks)
    if has_fail:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
