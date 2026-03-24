from pathlib import Path

import pytest

from viper.exceptions import ValidationError
from viper.links import normalize_link_subpath, resolve_service_overrides, validate_link_candidate
from viper.state import State


def test_validate_link_candidate_success(tmp_path: Path) -> None:
    (tmp_path / "repos" / "api").mkdir(parents=True)
    (tmp_path / "repos" / "my-lib" / "src").mkdir(parents=True)
    state = State(repos=["api"])

    link = validate_link_candidate(
        tmp_path,
        state,
        api_repo="api",
        lib_repo="my-lib",
        subpath="src",
    )
    assert link.lib_repo == "my-lib"
    assert link.subpath == "src"


def test_validate_link_candidate_fails_for_missing_subpath(tmp_path: Path) -> None:
    (tmp_path / "repos" / "api").mkdir(parents=True)
    (tmp_path / "repos" / "my-lib").mkdir(parents=True)
    state = State(repos=["api"])

    with pytest.raises(ValidationError):
        validate_link_candidate(
            tmp_path,
            state,
            api_repo="api",
            lib_repo="my-lib",
            subpath="src",
        )


def test_resolve_service_overrides_mounts_and_pythonpath(tmp_path: Path) -> None:
    (tmp_path / "repos" / "api").mkdir(parents=True)
    (tmp_path / "repos" / "api" / ".env").write_text("PORT=8000\nPYTHONPATH=/app/current\n", encoding="utf-8")
    (tmp_path / "repos" / "my-lib" / "src").mkdir(parents=True)

    state = State(
        repos=["api"],
        library_links={
            "api": [
                {"lib_repo": "my-lib", "subpath": "src"},
            ]
        },
    )
    state.normalize()

    overrides = resolve_service_overrides(tmp_path, state)
    assert "api" in overrides
    override = overrides["api"]
    assert len(override.volumes) == 1
    assert override.volumes[0].endswith(":/opt/viper-links/my-lib/src:ro")
    assert override.environment["PYTHONPATH"].startswith("/opt/viper-links/my-lib/src:")
    assert override.environment["PYTHONPATH"].endswith("/app/current")


def test_normalize_link_subpath_rejects_absolute_and_parent() -> None:
    with pytest.raises(ValidationError):
        normalize_link_subpath("/absolute/path")
    with pytest.raises(ValidationError):
        normalize_link_subpath("../bad")
