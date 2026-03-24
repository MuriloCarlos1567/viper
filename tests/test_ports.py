from viper.env_parser import PortRequest
from viper.exceptions import PortConflictError
from viper.ports import resolve_repo_port_bindings


def test_resolve_repo_port_bindings_prompts_when_conflict() -> None:
    used = {8000: ("repo-a", 8000)}
    requests = [PortRequest(container_port=8000, suggested_host_port=8000)]

    prompted: list[tuple[str, int]] = []

    def fake_prompt(message: str, default: int) -> int:
        prompted.append((message, default))
        return 8100

    bindings, overrides = resolve_repo_port_bindings(
        repo="repo-b",
        requests=requests,
        current_overrides=None,
        used_host_ports=used,
        interactive=True,
        prompt_fn=fake_prompt,
    )

    assert len(prompted) == 1
    assert bindings[0].host_port == 8100
    assert bindings[0].container_port == 8000
    assert overrides == {"8000": 8100}


def test_resolve_repo_port_bindings_fails_without_interactive() -> None:
    used = {8000: ("repo-a", 8000)}
    requests = [PortRequest(container_port=8000, suggested_host_port=8000)]

    try:
        resolve_repo_port_bindings(
            repo="repo-b",
            requests=requests,
            current_overrides=None,
            used_host_ports=used,
            interactive=False,
        )
    except PortConflictError:
        assert True
    else:
        assert False, "Expected PortConflictError"
