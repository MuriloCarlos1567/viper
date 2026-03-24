from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json

from rich.console import Console
from rich.table import Table
from rich.text import Text

from viper.status import RepoStatusRow


console = Console()


def print_success(message: str) -> None:
    console.print(f"[bold green]OK[/bold green] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]AVISO[/bold yellow] {message}")


def print_error(message: str) -> None:
    console.print(f"[bold red]ERRO[/bold red] {message}")


def print_ports_table(rows: list[dict[str, str]]) -> None:
    table = Table(title="Portas dos Repositórios", header_style="bold cyan")
    table.add_column("Repositorio", style="bold")
    table.add_column("Service")
    table.add_column("Host")
    table.add_column("Container")
    table.add_column("Fonte")

    for row in rows:
        table.add_row(
            row["repo"],
            row["service"],
            row["host_port"],
            row["container_port"],
            row["source"],
        )
    console.print(table)


def print_ports_json(rows: list[dict[str, str]]) -> None:
    console.print(json.dumps(rows, ensure_ascii=False, indent=2))


def print_status_table(rows: Iterable[RepoStatusRow], title: str = "Status dos Repositórios") -> None:
    table = Table(title=title, header_style="bold cyan")
    table.add_column("Repositorio", style="bold")
    table.add_column("Service")
    table.add_column("Container")
    table.add_column("Estado")
    table.add_column("Saude")
    table.add_column("Portas")

    for row in rows:
        state_style = "green" if row.state.lower() == "running" else "yellow"
        health_style = "green" if row.health.lower() in ("healthy", "running") else "red"
        table.add_row(
            row.repo,
            row.service,
            row.container,
            Text(estado_legivel(row.state), style=state_style),
            Text(saude_legivel(row.health), style=health_style),
            row.ports,
        )
    console.print(table)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    details: str


def print_doctor_table(checks: list[DoctorCheck]) -> None:
    table = Table(title="Diagnóstico", header_style="bold cyan")
    table.add_column("Verificação", style="bold")
    table.add_column("Status")
    table.add_column("Detalhes")

    for check in checks:
        style = "green" if check.status == "APROVADO" else "red" if check.status == "FALHA" else "yellow"
        table.add_row(check.name, Text(check.status, style=style), check.details)
    console.print(table)


def estado_legivel(valor: str) -> str:
    mapa = {
        "running": "rodando",
        "not-created": "nao-criado",
        "created": "criado",
        "restarting": "reiniciando",
        "paused": "pausado",
        "exited": "finalizado",
        "dead": "morto",
        "unknown": "desconhecido",
    }
    return mapa.get(valor.strip().lower(), valor)


def saude_legivel(valor: str) -> str:
    mapa = {
        "healthy": "saudavel",
        "unhealthy": "nao-saudavel",
        "starting": "iniciando",
        "running": "rodando",
    }
    texto = valor.strip()
    if not texto:
        return texto
    return mapa.get(texto.lower(), texto)


def stream_colored_logs(lines: Iterable[str]) -> None:
    palette = ["cyan", "green", "magenta", "yellow", "bright_blue", "bright_green", "bright_cyan"]
    color_by_service: dict[str, str] = {}

    for line in lines:
        parsed = _parse_compose_log_line(line.rstrip("\n"))
        if parsed is None:
            console.print(line.rstrip("\n"))
            continue

        service, message = parsed
        if service not in color_by_service:
            color_by_service[service] = palette[len(color_by_service) % len(palette)]
        color = color_by_service[service]
        console.print(f"[bold {color}]{service:<20}[/bold {color}] {message}")


def _parse_compose_log_line(line: str) -> tuple[str, str] | None:
    if "|" not in line:
        return None
    left, right = line.split("|", 1)
    service = left.strip()
    message = right.lstrip()
    if not service:
        return None
    return service, message
