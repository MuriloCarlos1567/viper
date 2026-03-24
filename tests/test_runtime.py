from pathlib import Path

from viper.runtime import ComposeRuntime


def test_ps_json_parses_ndjson(monkeypatch, tmp_path: Path) -> None:
    runtime = ComposeRuntime(compose_path=tmp_path / "docker-compose.yml", project_name="localdev")
    sample = (
        '{"Service":"api-users","State":"running"}\n'
        '{"Service":"api-orders","State":"running"}\n'
    )

    monkeypatch.setattr(runtime, "run", lambda *args, **kwargs: sample)
    rows = runtime.ps_json()

    assert len(rows) == 2
    assert rows[0]["Service"] == "api-users"
    assert rows[1]["Service"] == "api-orders"
