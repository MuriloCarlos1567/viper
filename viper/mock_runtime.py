from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from viper.compose_generator import MockServiceSpec
from viper.mock_config import MockConfig
from viper.paths import mock_dockerfile, mock_routes_file, mock_runtime_dir, mock_server_file


MOCK_SERVICE_NAME = "viper-mock"
MOCK_HOSTNAME = "viper-mock"


@dataclass(frozen=True)
class MockArtifacts:
    runtime_dir: Path
    routes_file: Path
    server_file: Path
    dockerfile: Path


def prepare_mock_service(root: Path, config: MockConfig) -> MockServiceSpec:
    artifacts = write_mock_artifacts(root, config)
    return MockServiceSpec(
        service_name=MOCK_SERVICE_NAME,
        hostname=MOCK_HOSTNAME,
        host_port=config.port,
        container_port=config.port,
        build_context=artifacts.runtime_dir,
    )


def write_mock_artifacts(root: Path, config: MockConfig) -> MockArtifacts:
    runtime_dir = mock_runtime_dir(root)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    routes_path = mock_routes_file(root)
    server_path = mock_server_file(root)
    dockerfile_path = mock_dockerfile(root)

    routes_payload = {
        "port": config.port,
        "routes": [
            {
                "method": route.method,
                "path": route.path,
                "status": route.status,
                "body": route.body,
            }
            for route in config.routes
        ],
    }
    routes_path.write_text(json.dumps(routes_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    server_path.write_text(_mock_server_source(), encoding="utf-8")
    dockerfile_path.write_text(_mock_dockerfile_source(), encoding="utf-8")

    return MockArtifacts(
        runtime_dir=runtime_dir,
        routes_file=routes_path,
        server_file=server_path,
        dockerfile=dockerfile_path,
    )


def _mock_dockerfile_source() -> str:
    return (
        "FROM python:3.12-slim\n"
        "WORKDIR /mock\n"
        "COPY mock_server.py /mock/mock_server.py\n"
        "COPY routes.resolved.json /mock/routes.resolved.json\n"
        "ENV VIPER_MOCK_ROUTES_FILE=/mock/routes.resolved.json\n"
        "ENV VIPER_MOCK_PORT=4010\n"
        "CMD [\"python\", \"/mock/mock_server.py\"]\n"
    )


def _mock_server_source() -> str:
    return """import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _load_routes():
    routes_file = os.getenv("VIPER_MOCK_ROUTES_FILE", "/mock/routes.resolved.json")
    with open(routes_file, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    routes = payload.get("routes", [])
    return {
        (str(route.get("method", "")).upper(), str(route.get("path", ""))): {
            "status": int(route.get("status", 200)),
            "body": route.get("body"),
        }
        for route in routes
    }


ROUTE_MAP = _load_routes()


class MockHandler(BaseHTTPRequestHandler):
    server_version = "ViperMock/1.0"

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()

    def do_OPTIONS(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def _dispatch(self):
        if self.path == "/__health":
            payload = {"status": "ok"}
            self._send_json(200, payload)
            return

        key = (self.command.upper(), self.path)
        route = ROUTE_MAP.get(key)
        if route is None:
            self._send_json(404, {"error": f"Rota de mock nao encontrada: {self.command} {self.path}"})
            return

        status = int(route.get("status", 200))
        body = route.get("body")
        if isinstance(body, (dict, list)):
            self._send_json(status, body)
            return

        raw = "" if body is None else str(body)
        encoded = raw.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args):
        print(f"{self.command} {self.path} -> " + fmt % args)

    def _send_json(self, status_code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    port = int(os.getenv("VIPER_MOCK_PORT", "4010"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MockHandler)
    print(f"Viper mock server ouvindo na porta {port}")
    server.serve_forever()
"""
