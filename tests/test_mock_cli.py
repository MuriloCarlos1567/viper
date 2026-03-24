from pathlib import Path

from typer.testing import CliRunner

from viper.cli import app


runner = CliRunner()


class _DummyProcess:
    def __init__(self, lines: list[str], calls: list[tuple[str, str | None]]) -> None:
        self.stdout = iter(lines)
        self._calls = calls

    def terminate(self) -> None:
        self._calls.append(("terminate", None))


def test_mock_commands_flow(tmp_path: Path, monkeypatch) -> None:
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
            return [
                {
                    "Service": "viper-mock",
                    "Name": "localdev-viper-mock-1",
                    "State": "running",
                    "Health": "healthy",
                    "Publishers": [
                        {
                            "PublishedPort": 4010,
                            "TargetPort": 4010,
                        }
                    ],
                }
            ]

        def logs_follow(self, services=None):
            calls.append(("logs", ",".join(services or [])))
            return _DummyProcess(["viper-mock | hello\n"], calls)

        def config_validate(self) -> bool:
            return True

    monkeypatch.setattr("viper.cli._runtime", lambda compose_path, stack_name: DummyRuntime(compose_path, stack_name))

    config_path = tmp_path / "viper.mock.yaml"
    config_path.write_text(
        "\n".join(
            [
                "server:",
                "  port: 4010",
                "routes:",
                "  - method: GET",
                "    path: /ping",
                "    status: 200",
                "    body:",
                "      ok: true",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["mock", "validate"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["mock", "up", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["mock", "status", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["mock", "logs", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["mock", "down", "--name", "localdev"])
    assert result.exit_code == 0, result.output

    assert ("up", "viper-mock") in calls
    assert ("logs", "viper-mock") in calls
    assert ("stop_remove", "viper-mock") in calls


def test_mock_validate_invalid_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "viper.mock.yaml").write_text(
        "\n".join(
            [
                "routes:",
                "  - method: BAD",
                "    path: /x",
                "    status: 200",
                "    body: test",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["mock", "validate"])
    assert result.exit_code == 1
