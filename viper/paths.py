from pathlib import Path


DEFAULT_STACK_NAME = "viper"
STATE_DIRNAME = ".viper"
REPOS_DIRNAME = "repos"
STATE_FILENAME = "state.toml"
COMPOSE_FILENAME = "docker-compose.generated.yml"
MOCK_RUNTIME_DIRNAME = "mock"
MOCK_CONFIG_FILENAME = "viper.mock.yaml"
MOCK_ROUTES_FILENAME = "routes.resolved.json"
MOCK_SERVER_FILENAME = "mock_server.py"
MOCK_DOCKERFILE_FILENAME = "Dockerfile"


def project_root(root: Path | None = None) -> Path:
    return (root or Path.cwd()).resolve()


def repos_dir(root: Path | None = None) -> Path:
    return project_root(root) / REPOS_DIRNAME


def state_dir(root: Path | None = None) -> Path:
    return project_root(root) / STATE_DIRNAME


def state_file(root: Path | None = None) -> Path:
    return state_dir(root) / STATE_FILENAME


def compose_file(root: Path | None = None) -> Path:
    return state_dir(root) / COMPOSE_FILENAME


def mock_runtime_dir(root: Path | None = None) -> Path:
    return state_dir(root) / MOCK_RUNTIME_DIRNAME


def mock_config_file(root: Path | None = None) -> Path:
    return project_root(root) / MOCK_CONFIG_FILENAME


def mock_routes_file(root: Path | None = None) -> Path:
    return mock_runtime_dir(root) / MOCK_ROUTES_FILENAME


def mock_server_file(root: Path | None = None) -> Path:
    return mock_runtime_dir(root) / MOCK_SERVER_FILENAME


def mock_dockerfile(root: Path | None = None) -> Path:
    return mock_runtime_dir(root) / MOCK_DOCKERFILE_FILENAME
