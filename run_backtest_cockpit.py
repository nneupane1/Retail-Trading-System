"""Single-command launcher for the backtest cockpit.

This mirrors `run_live_cockpit.py` but runs the historical backtest engine
so the same dashboard frontend/backend can be used to inspect backtest
telemetry/artifacts.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "dashboard"
DEFAULT_API_PORT = 8000
DEFAULT_FRONTEND_PORT = 3000


@dataclass
class ServiceHandle:
    name: str
    process: subprocess.Popen | None
    external: bool
    url: str | None = None

    @property
    def managed(self) -> bool:
        return self.process is not None and not self.external


@dataclass
class RuntimePorts:
    api_port: int
    frontend_port: int

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def frontend_url(self) -> str:
        return f"http://127.0.0.1:{self.frontend_port}"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 400
    except Exception:
        return False


def _port_bindable(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _choose_port(preferred: int, *, search_window: int = 40) -> int:
    for candidate in range(preferred, preferred + search_window):
        if _port_bindable(candidate):
            return candidate
    raise RuntimeError(f"No bindable local port found near {preferred}.")


def _wait_for_http(url: str, timeout_seconds: float = 120.0, interval_seconds: float = 1.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _http_ok(url):
            return True
        time.sleep(interval_seconds)
    return False


def _ensure_command(name: str) -> str:
    command = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not command:
        raise RuntimeError(f"Required command '{name}' was not found on PATH.")
    return command


def _run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def _frontend_env(api_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["NEXT_PUBLIC_DASHBOARD_API_URL"] = api_url
    return env


def _ensure_python_modules(modules: list[str]) -> None:
    missing = [module for module in modules if importlib.util.find_spec(module) is None]
    if not missing:
        return
    python = sys.executable
    commands = [
        [python, "-m", "pip", "install", *missing],
        [
            python,
            "-m",
            "pip",
            "install",
            "--trusted-host",
            "pypi.org",
            "--trusted-host",
            "files.pythonhosted.org",
            "--trusted-host",
            "pypi.python.org",
            *missing,
        ],
    ]
    last_error: Exception | None = None
    for command in commands:
        try:
            subprocess.run(command, cwd=str(ROOT), check=True)
            return
        except Exception as error:  # pragma: no cover - environment path
            last_error = error
    raise RuntimeError(
        f"Python dependency install failed for: {', '.join(missing)}"
    ) from last_error


def _ensure_backend_dependencies() -> None:
    _ensure_python_modules(["fastapi", "uvicorn"])


def _ensure_frontend_dependencies() -> None:
    next_binary = DASHBOARD_DIR / "node_modules" / ".bin" / "next"
    if next_binary.exists():
        return

    npm = _ensure_command("npm")
    env = os.environ.copy()
    commands = [
        [npm, "install", "--no-audit", "--no-fund"],
        [npm, "install", "--strict-ssl=false", "--no-audit", "--no-fund"],
    ]
    last_error: Exception | None = None
    for command in commands:
        try:
            _run_checked(command, cwd=DASHBOARD_DIR, env=env)
            return
        except Exception as error:  # pragma: no cover - environment path
            last_error = error
    raise RuntimeError("Frontend dependency installation failed.") from last_error


def _ensure_frontend_build(api_url: str) -> None:
    build_id = DASHBOARD_DIR / ".next" / "BUILD_ID"
    marker = DASHBOARD_DIR / ".next" / "dashboard_api_url.txt"
    if build_id.exists() and marker.exists():
        try:
            content = marker.read_text(encoding="utf-8").splitlines()
            if len(content) >= 1 and content[0].strip() == api_url.strip():
                return
        except Exception:
            pass
    npm = _ensure_command("npm")
    _run_checked(
        [npm, "run", "build"],
        cwd=DASHBOARD_DIR,
        env=_frontend_env(api_url),
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{api_url.strip()}", encoding="utf-8")


def _launch_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    log_dir: Path,
) -> ServiceHandle:
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=creationflags,
    )
    return ServiceHandle(name=name, process=process, external=False)


def _terminate_process_tree(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _start_or_validate_backend(log_dir: Path, ports: RuntimePorts) -> ServiceHandle:
    if _http_ok(f"{ports.api_url}/health"):
        return ServiceHandle(name="dashboard_api", process=None, external=True, url=ports.api_url)

    _ensure_backend_dependencies()
    python = sys.executable
    backend_env = os.environ.copy()
    backend_env["DASHBOARD_MODE"] = "backtest"
    handle = _launch_process(
        "dashboard_api",
        [
            python,
            "-m",
            "uvicorn",
            "dashboard_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(ports.api_port),
        ],
        cwd=ROOT,
        env=backend_env,
        log_dir=log_dir,
    )
    if not _wait_for_http(f"{ports.api_url}/health", timeout_seconds=90):
        raise RuntimeError("Dashboard API did not become healthy in time.")
    handle.url = ports.api_url
    return handle


def _start_or_validate_frontend(log_dir: Path, ports: RuntimePorts) -> ServiceHandle:
    if _http_ok(ports.frontend_url):
        return ServiceHandle(name="dashboard_frontend", process=None, external=True, url=ports.frontend_url)

    _ensure_frontend_dependencies()
    _ensure_frontend_build(ports.api_url)
    npm = _ensure_command("npm")
    handle = _launch_process(
        "dashboard_frontend",
        [npm, "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(ports.frontend_port)],
        cwd=DASHBOARD_DIR,
        env=_frontend_env(ports.api_url),
        log_dir=log_dir,
    )
    if not _wait_for_http(ports.frontend_url, timeout_seconds=120):
        raise RuntimeError("Dashboard frontend did not become ready in time.")
    handle.url = ports.frontend_url
    return handle


def _start_backtest_engine(log_dir: Path) -> ServiceHandle:
    python = sys.executable
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return _launch_process(
        "backtest_engine",
        [python, "main_backtest.py"],
        cwd=ROOT,
        env=env,
        log_dir=log_dir,
    )


def _browser_open(url: str) -> None:
    try:
        webbrowser.open(url, new=1, autoraise=True)
    except Exception:
        pass


def _print_status(services: list[ServiceHandle], log_dir: Path, ports: RuntimePorts) -> None:
    print("\nBACKTEST COCKPIT STATUS")
    print(f"Logs: {log_dir}")
    print(f"API: {ports.api_url}")
    print(f"Frontend: {ports.frontend_url}")
    for handle in services:
        mode = "external" if handle.external else "managed"
        pid = handle.process.pid if handle.process is not None else "-"
        print(f"- {handle.name}: {mode} | pid={pid} | url={handle.url or '-'}")


def _monitor(services: list[ServiceHandle], log_dir: Path, ports: RuntimePorts) -> None:
    _print_status(services, log_dir, ports)
    last_heartbeat = 0.0
    while True:
        for handle in services:
            if handle.process is not None and handle.process.poll() is not None:
                raise RuntimeError(
                    f"Managed service '{handle.name}' exited with code {handle.process.returncode}."
                )
        if time.time() - last_heartbeat >= 15.0:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] backtest cockpit healthy | "
                f"frontend={ports.frontend_url} | api={ports.api_url}/health"
            )
            last_heartbeat = time.time()
        time.sleep(2.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the full backtest cockpit.")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ports = RuntimePorts(
        api_port=_choose_port(DEFAULT_API_PORT),
        frontend_port=_choose_port(DEFAULT_FRONTEND_PORT),
    )
    log_dir = ROOT / "live_sim" / "output" / f"backtest_cockpit_{_timestamp()}"
    log_dir.mkdir(parents=True, exist_ok=True)

    services: list[ServiceHandle] = []
    try:
        # Start backtest engine first so it can write artifacts the API may surface.
        services.append(_start_backtest_engine(log_dir))
        services.append(_start_or_validate_backend(log_dir, ports))
        services.append(_start_or_validate_frontend(log_dir, ports))

        if not args.no_browser:
            _browser_open(ports.frontend_url)

        _monitor(services, log_dir, ports)
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as error:
        print(f"\nBacktest cockpit launcher error: {error}")
        raise
    finally:
        for handle in reversed(services):
            if handle.managed:
                _terminate_process_tree(handle.process)


if __name__ == "__main__":
    main()
