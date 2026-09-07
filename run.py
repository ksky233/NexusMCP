#!/usr/bin/env python3
"""启动 NexusMCP 本地后端开发环境。

默认管理：
    PostgreSQL（Docker Compose）
    Alembic Migration
    FastAPI

React/Vite 保持为独立进程：
    cd web
    pnpm dev
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nexusmcp.bootstrap.config import Settings

PROJECT_DIR = Path(__file__).resolve().parent
COMPOSE_SERVICE = "postgres"
LOCAL_ENV_DEFAULTS = {
    "NEXUSMCP_ENVIRONMENT": "development",
    "NEXUSMCP_CATALOG_BACKEND": "postgresql",
    "NEXUSMCP_DATABASE_URL": (
        "postgresql+asyncpg://nexusmcp:nexusmcp_dev@127.0.0.1:55432/nexusmcp"
    ),
    "NEXUSMCP_CONTROL_PLANE_ENABLED": "true",
    "NEXUSMCP_TOOL_EXECUTION_ENABLED": "true",
    "NEXUSMCP_UPSTREAM_EGRESS_POLICY_ENABLED": "true",
    "NEXUSMCP_UPSTREAM_ALLOWED_PORTS": "[80,443,9001,9002,9003]",
    "NEXUSMCP_UPSTREAM_ALLOW_LOCAL_DEMO": "true",
    "NEXUSMCP_LOCAL_TENANT_ID": "00000000-0000-0000-0000-000000000001",
    "NEXUSMCP_MCP_IDENTITY_MODE": "static_service",
    "NEXUSMCP_STATIC_AGENT_PRINCIPAL_ID": "local-agent-service",
    "NEXUSMCP_LOCAL_ADMIN_PRINCIPAL_ID": "local-admin",
}


@dataclass(slots=True)
class ManagedProcess:
    name: str
    process: subprocess.Popen[Any]


class BackendSupervisor:
    def __init__(self, arguments: argparse.Namespace) -> None:
        self.arguments = arguments
        self.processes: list[ManagedProcess] = []
        self.infrastructure_started_here = False
        self.shutdown_requested = False

    def run(self) -> int:
        self._register_signal_handlers()
        try:
            self._check_commands()
            self._validate_configuration()
            if not self.arguments.no_docker:
                self._start_infrastructure()
            if not self.arguments.skip_migrations:
                self._run_migrations()
            self._check_api_port()
            self._start_api()
            self._wait_for_api()
            self._print_ready_message()
            return self._monitor()
        except KeyboardInterrupt:
            return 0
        except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"\n[ERROR] {error}", file=sys.stderr)
            return 1
        finally:
            self.shutdown()

    def _register_signal_handlers(self) -> None:
        def request_shutdown(_signal_number: int, _frame: Any) -> None:
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, request_shutdown)
        signal.signal(signal.SIGTERM, request_shutdown)

    def _check_commands(self) -> None:
        if not self.arguments.no_docker and shutil.which("docker") is None:
            raise FileNotFoundError("Required command not found: docker")

    def _validate_configuration(self) -> None:
        apply_local_environment_defaults(PROJECT_DIR / ".env")
        try:
            settings = Settings()
        except ValueError as error:
            raise RuntimeError(f"Invalid NexusMCP settings: {error}") from None
        if settings.catalog_backend != "postgresql":
            raise RuntimeError(
                "Local backend launcher requires NEXUSMCP_CATALOG_BACKEND=postgresql"
            )
        if settings.database_url is None:
            raise RuntimeError("Local backend launcher requires NEXUSMCP_DATABASE_URL")
        if not settings.control_plane_enabled:
            raise RuntimeError(
                "Local Web Control Plane requires NEXUSMCP_CONTROL_PLANE_ENABLED=true"
            )

    def _start_infrastructure(self) -> None:
        before = compose_service_states()
        self.infrastructure_started_here = before.get(COMPOSE_SERVICE, {}).get("State") != "running"
        print("[infra] Ensuring PostgreSQL is running…")
        run_checked(["docker", "compose", "up", "-d", COMPOSE_SERVICE])
        wait_for_compose_health(COMPOSE_SERVICE, timeout_seconds=60)
        print("[infra] PostgreSQL is healthy")

    def _run_migrations(self) -> None:
        print("[database] Applying Alembic migrations…")
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"])

    def _check_api_port(self) -> None:
        if port_is_open(self.arguments.port):
            raise RuntimeError(
                f"FastAPI port {self.arguments.port} is already in use. Stop the existing "
                "backend process or continue using that running backend."
            )

    def _start_api(self) -> None:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "nexusmcp.main:app",
            "--host",
            self.arguments.host,
            "--port",
            str(self.arguments.port),
        ]
        if self.arguments.reload:
            command.extend(["--reload", "--reload-dir", "src"])
        self._start_process("FastAPI", command)

    def _start_process(self, name: str, command: list[str]) -> None:
        print(f"[{name}] Starting: {' '.join(command)}")
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        kwargs: dict[str, Any] = {
            "cwd": PROJECT_DIR,
            "env": environment,
            "stdin": None,
            "stdout": None,
            "stderr": None,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        self.processes.append(ManagedProcess(name=name, process=process))

    def _wait_for_api(self) -> None:
        probe_host = (
            "127.0.0.1" if self.arguments.host in {"0.0.0.0", "::"} else self.arguments.host
        )
        health_url = f"http://{probe_host}:{self.arguments.port}/health/ready"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            failed = [item for item in self.processes if item.process.poll() is not None]
            if failed:
                details = ", ".join(
                    f"{item.name} exited with {item.process.returncode}" for item in failed
                )
                raise RuntimeError(details)
            if http_endpoint_is_ready(health_url):
                return
            time.sleep(0.25)
        raise RuntimeError(f"FastAPI readiness probe did not pass within 30 seconds: {health_url}")

    def _print_ready_message(self) -> None:
        browser_host = (
            "127.0.0.1" if self.arguments.host in {"0.0.0.0", "::"} else self.arguments.host
        )
        base_url = f"http://{browser_host}:{self.arguments.port}"
        print("\n=== NexusMCP backend is running ===")
        print(f"FastAPI:   {base_url}")
        print(f"Admin API: {base_url}/admin/docs")
        print(f"Readiness: {base_url}/health/ready")
        print("Frontend:  cd web && pnpm dev")
        print("Press Ctrl+C to stop managed backend processes.\n")

    def _monitor(self) -> int:
        while not self.shutdown_requested:
            for item in self.processes:
                return_code = item.process.poll()
                if return_code is not None:
                    print(f"\n[ERROR] {item.name} exited unexpectedly: {return_code}")
                    return return_code or 1
            time.sleep(1)
        return 0

    def shutdown(self) -> None:
        if self.processes:
            print("\n[shutdown] Stopping backend processes…")
        for item in reversed(self.processes):
            stop_process_tree(item)
        self.processes.clear()

        if (
            self.infrastructure_started_here
            and not self.arguments.keep_infra
            and not self.arguments.no_docker
        ):
            print(f"[shutdown] Stopping infrastructure started here: {COMPOSE_SERVICE}")
            subprocess.run(
                ["docker", "compose", "stop", COMPOSE_SERVICE],
                cwd=PROJECT_DIR,
                check=False,
            )


def run_checked(command: list[str]) -> None:
    subprocess.run(command, cwd=PROJECT_DIR, check=True)


def apply_local_environment_defaults(
    env_file: Path,
    environment: MutableMapping[str, str] = os.environ,
) -> None:
    """仅为未声明字段补 Docker Compose 本地默认值，显式配置始终优先。"""

    declared_names = dotenv_declared_names(env_file)
    for name, value in LOCAL_ENV_DEFAULTS.items():
        if name not in environment and name not in declared_names:
            environment[name] = value


def dotenv_declared_names(env_file: Path) -> set[str]:
    if not env_file.is_file():
        return set()
    names: set[str] = set()
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        name, _value = line.split("=", maxsplit=1)
        if name.strip():
            names.add(name.strip())
    return names


def compose_service_states() -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=PROJECT_DIR,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"Docker Compose status failed. Ensure Docker Desktop is running. Details: {details}"
        )
    return parse_compose_service_states(result.stdout)


def parse_compose_service_states(output: str) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records = payload if isinstance(payload, list) else [payload]
        for record in records:
            if not isinstance(record, dict):
                continue
            service = record.get("Service")
            if isinstance(service, str):
                states[service] = record
    return states


def wait_for_compose_health(service: str, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = compose_service_states().get(service, {})
        if state.get("State") == "running" and state.get("Health") in {"healthy", ""}:
            return
        time.sleep(1)
    status = compose_service_states().get(service, {}).get("Status", "missing")
    raise RuntimeError(f"Docker service did not become healthy: {service}={status}")


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def http_endpoint_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:  # noqa: S310 - Local URL only
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def stop_process_tree(item: ManagedProcess) -> None:
    process = item.process
    if process.poll() is not None:
        return
    print(f"[shutdown] Stopping {item.name}…")
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[WARN] {item.name} could not be stopped cleanly")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Uvicorn bind host")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn bind port")
    parser.add_argument("--reload", action="store_true", help="Enable Uvicorn source reload")
    parser.add_argument("--keep-infra", action="store_true", help="Keep PostgreSQL running")
    parser.add_argument("--no-docker", action="store_true", help="Do not manage PostgreSQL")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip Alembic upgrade")
    return parser


def configure_console_encoding() -> None:
    """Windows 管道默认 Code Page 不稳定，显式使用 UTF-8 保持启动信息可读。"""

    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", line_buffering=True, write_through=True)


def main() -> int:
    configure_console_encoding()
    return BackendSupervisor(build_parser().parse_args()).run()


if __name__ == "__main__":
    raise SystemExit(main())
