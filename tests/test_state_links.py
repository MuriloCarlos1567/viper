from pathlib import Path

from viper.state import State, load_state, save_state


def test_load_state_without_library_links_is_compatible(tmp_path: Path) -> None:
    state_dir = tmp_path / ".viper"
    state_dir.mkdir(parents=True)
    (state_dir / "state.toml").write_text(
        "\n".join(
            [
                'default_stack = "localdev"',
                'repos = ["api"]',
                "",
                "[port_overrides.api]",
                '8000 = 8001',
            ]
        ),
        encoding="utf-8",
    )

    state = load_state(tmp_path)
    assert state.default_stack == "localdev"
    assert state.repos == ["api"]
    assert state.library_links == {}


def test_save_and_load_state_with_library_links(tmp_path: Path) -> None:
    state = State(
        default_stack="localdev",
        repos=["api"],
        port_overrides={},
        library_links={
            "api": [
                {"lib_repo": "my-lib", "subpath": "src"},
                {"lib_repo": "my-lib", "subpath": "src"},
            ]
        },
    )
    save_state(state, tmp_path)
    reloaded = load_state(tmp_path)
    assert reloaded.library_links == {"api": [{"lib_repo": "my-lib", "subpath": "src"}]}
