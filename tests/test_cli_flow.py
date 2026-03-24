from pathlib import Path

from typer.testing import CliRunner

from viper.cli import app


runner = CliRunner()


def test_init_add_update_flow(tmp_path: Path, monkeypatch) -> None:
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

        def ps_json(self):
            return []

        def logs_follow(self, services=None):
            raise RuntimeError("not used")

        def config_validate(self) -> bool:
            return True

    monkeypatch.setattr("viper.cli._runtime", lambda compose_path, stack_name: DummyRuntime(compose_path, stack_name))

    repo_dir = tmp_path / "repos" / "api"
    repo_dir.mkdir(parents=True)
    (repo_dir / "Dockerfile").write_text("FROM python:3.12-slim\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n", encoding="utf-8")
    (repo_dir / ".env").write_text("PORT=8000\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["add", "api"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["update", "api", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    assert ("stop_remove", "api") in calls
    assert ("up", "api") in calls
