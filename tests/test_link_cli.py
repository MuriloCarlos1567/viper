from pathlib import Path

import yaml
from typer.testing import CliRunner

from viper.cli import app


runner = CliRunner()


def test_link_add_list_remove_and_restart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, str | None]] = []

    class DummyRuntime:
        def __init__(self, compose_path: Path, project_name: str) -> None:
            self.compose_path = compose_path
            self.project_name = project_name

        def up(self, services=None) -> None:
            calls.append(("up", ",".join(services or [])))

        def down(self) -> None:
            calls.append(("down", None))

        def stop_remove_service(self, service: str) -> None:
            calls.append(("stop_remove", service))

        def restart(self, services=None) -> None:
            calls.append(("restart", ",".join(services or [])))

        def run(self, args, *, capture=False, check=True):
            joined = " ".join(args)
            calls.append(("run", joined))
            return ""

        def ps_json(self):
            return [
                {
                    "Service": "api",
                    "State": "running",
                    "Name": "localdev-api-1",
                }
            ]

        def logs_follow(self, services=None):
            raise RuntimeError("not used")

        def config_validate(self) -> bool:
            return True

    monkeypatch.setattr("viper.cli._runtime", lambda compose_path, stack_name: DummyRuntime(compose_path, stack_name))

    api_dir = tmp_path / "repos" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "Dockerfile").write_text("FROM python:3.12-slim\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n", encoding="utf-8")
    (api_dir / ".env").write_text("PORT=8000\n", encoding="utf-8")

    lib_src = tmp_path / "repos" / "my-lib" / "src"
    lib_src.mkdir(parents=True)
    (lib_src / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")

    assert runner.invoke(app, ["init", "--name", "localdev"]).exit_code == 0
    assert runner.invoke(app, ["add", "api"]).exit_code == 0

    result = runner.invoke(
        app,
        ["link", "add", "--api", "api", "--lib", "my-lib", "--subpath", "src", "--name", "localdev"],
    )
    assert result.exit_code == 0, result.output
    assert any(item[0] == "run" and "--force-recreate api" in str(item[1]) for item in calls)

    list_result = runner.invoke(app, ["link", "list", "--json"])
    assert list_result.exit_code == 0, list_result.output
    assert '"api_repo": "api"' in list_result.output
    assert '"lib_repo": "my-lib"' in list_result.output

    up_result = runner.invoke(app, ["up", "api", "--name", "localdev"])
    assert up_result.exit_code == 0, up_result.output
    compose_data = yaml.safe_load((tmp_path / ".viper" / "docker-compose.generated.yml").read_text(encoding="utf-8"))
    service = compose_data["services"]["api"]
    assert any(str(item).endswith(":/opt/viper-links/my-lib/src:ro") for item in service["volumes"])
    assert service["environment"]["PYTHONPATH"].startswith("/opt/viper-links/my-lib/src")

    remove_result = runner.invoke(
        app,
        ["link", "remove", "--api", "api", "--lib", "my-lib", "--subpath", "src", "--name", "localdev"],
    )
    assert remove_result.exit_code == 0, remove_result.output
    recreate_calls = [item for item in calls if item[0] == "run" and "--force-recreate api" in str(item[1])]
    assert len(recreate_calls) >= 2
