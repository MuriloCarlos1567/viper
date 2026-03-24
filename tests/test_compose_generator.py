from pathlib import Path

from viper.compose_generator import MockServiceSpec, ServiceOverride, build_compose_document
from viper.ports import PortBinding


def test_build_compose_document_is_deterministic(tmp_path: Path) -> None:
    resolved = {
        "zeta-api": [PortBinding(repo="zeta-api", host_port=9000, container_port=9000)],
        "alpha-api": [PortBinding(repo="alpha-api", host_port=8000, container_port=8000)],
    }
    document, service_by_repo = build_compose_document(
        root=tmp_path,
        repos=["zeta-api", "alpha-api"],
        resolved_port_bindings=resolved,
    )

    service_names = list(document["services"].keys())
    assert service_names == ["alpha-api", "zeta-api"]
    assert service_by_repo["alpha-api"] == "alpha-api"
    assert document["services"]["alpha-api"]["ports"] == ["8000:8000"]
    expected_context = (tmp_path / "repos" / "alpha-api").resolve().as_posix()
    expected_env = (tmp_path / "repos" / "alpha-api" / ".env").resolve().as_posix()
    assert document["services"]["alpha-api"]["build"]["context"] == expected_context
    assert document["services"]["alpha-api"]["env_file"] == [expected_env]


def test_build_compose_document_with_mock_service(tmp_path: Path) -> None:
    mock_spec = MockServiceSpec(
        service_name="viper-mock",
        hostname="viper-mock",
        host_port=4010,
        container_port=4010,
        build_context=tmp_path / ".viper" / "mock",
    )
    document, _ = build_compose_document(
        root=tmp_path,
        repos=[],
        resolved_port_bindings={},
        mock_service=mock_spec,
    )

    assert "viper-mock" in document["services"]
    service = document["services"]["viper-mock"]
    assert service["hostname"] == "viper-mock"
    assert service["ports"] == ["4010:4010"]
    assert service["environment"]["VIPER_MOCK_PORT"] == "4010"


def test_build_compose_document_with_service_overrides(tmp_path: Path) -> None:
    resolved = {"api": [PortBinding(repo="api", host_port=8000, container_port=8000)]}
    overrides = {
        "api": ServiceOverride(
            volumes=["/host/lib:/opt/viper-links/lib/src:ro"],
            environment={"PYTHONPATH": "/opt/viper-links/lib/src"},
        )
    }
    document, _ = build_compose_document(
        root=tmp_path,
        repos=["api"],
        resolved_port_bindings=resolved,
        service_overrides_by_repo=overrides,
    )

    service = document["services"]["api"]
    assert service["volumes"] == ["/host/lib:/opt/viper-links/lib/src:ro"]
    assert service["environment"]["PYTHONPATH"] == "/opt/viper-links/lib/src"
