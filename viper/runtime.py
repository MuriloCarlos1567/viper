from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
from typing import Sequence

from viper.exceptions import ViperError


@dataclass
class ComposeRuntime:
    compose_path: Path
    project_name: str

    def up(self, services: Sequence[str] | None = None) -> None:
        args = ["up", "-d", "--build"]
        if services:
            args.extend(services)
        self.run(args)

    def down(self) -> None:
        self.run(["down", "--remove-orphans"])

    def stop_remove_service(self, service: str) -> None:
        self.run(["stop", service], check=False)
        self.run(["rm", "-f", service], check=False)

    def restart(self, services: Sequence[str] | None = None) -> None:
        args = ["restart"]
        if services:
            args.extend(services)
        self.run(args)

    def ps_json(self) -> list[dict]:
        output = self.run(["ps", "--format", "json"], capture=True, check=False)
        raw = output.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [entry for entry in parsed if isinstance(entry, dict)]
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            entries: list[dict] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
            return entries
        return []

    def config_validate(self) -> bool:
        command = self.base_cmd() + ["config", "-q"]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return completed.returncode == 0

    def logs_follow(self, services: Sequence[str] | None = None) -> subprocess.Popen[str]:
        args = ["logs", "-f", "--no-color", "--timestamps"]
        if services:
            args.extend(services)
        return subprocess.Popen(
            self.base_cmd() + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )

    def run(
        self,
        args: Sequence[str],
        *,
        capture: bool = False,
        check: bool = True,
    ) -> str:
        command = self.base_cmd() + list(args)
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if check and completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise ViperError(f"Falha ao executar Docker Compose: {' '.join(command)}\n{stderr}")
        return completed.stdout

    def base_cmd(self) -> list[str]:
        return [
            "docker",
            "compose",
            "-f",
            str(self.compose_path),
            "-p",
            self.project_name,
        ]
