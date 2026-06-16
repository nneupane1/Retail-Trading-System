from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from common.structural_lab_locator import resolve_structural_lab_project_root, structural_lab_output_root
from run_live_cockpit import (
    DASHBOARD_DIR,
    ROOT,
    RuntimePorts,
    ServiceHandle,
    _browser_open,
    _choose_port,
    _ensure_backend_dependencies,
    _ensure_command,
    _frontend_env,
    _http_ok,
    _launch_process,
    _run_checked,
    _timestamp,
    _wait_for_http,
)


DEFAULT_API_PORT = 8202
DEFAULT_FRONTEND_PORT = 3202


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the structural compounding research cockpit.")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser.")
    return parser.parse_args()


def _dashboard_runtime_dir() -> Path:
    return Path.home() / "RetailTradingSystemStructuralLabRuntime"


def _clear_runtime_contents(runtime_dir: Path) -> None:
    if not runtime_dir.exists():
        return
    for child in runtime_dir.iterdir():
        if child.name == "node_modules":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass


def _prepare_frontend_runtime(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    _clear_runtime_contents(runtime_dir)
    shutil.copytree(
        DASHBOARD_DIR,
        runtime_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("node_modules", ".next", ".next-runtime", "tsconfig.tsbuildinfo"),
    )
    source_node_modules = DASHBOARD_DIR / "node_modules"
    target_node_modules = runtime_dir / "node_modules"
    if source_node_modules.exists() and not target_node_modules.exists():
        _run_checked(
            ["cmd", "/c", "mklink", "/J", str(target_node_modules), str(source_node_modules)],
            cwd=runtime_dir,
        )


def _start_backend(log_dir: Path, ports: RuntimePorts) -> ServiceHandle:
    if _http_ok(f"{ports.api_url}/health"):
        return ServiceHandle(name="dashboard_api", process=None, external=True, url=ports.api_url)

    _ensure_backend_dependencies()
    handle = _launch_process(
        "dashboard_api_structural",
        [
            sys.executable,
            "-m",
            "uvicorn",
            "dashboard_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(ports.api_port),
        ],
        cwd=ROOT,
        env=None,
        log_dir=log_dir,
    )
    if not _wait_for_http(f"{ports.api_url}/health", timeout_seconds=90):
        raise RuntimeError("Structural lab dashboard API did not become healthy in time.")
    handle.url = ports.api_url
    return handle


def _start_frontend(log_dir: Path, ports: RuntimePorts) -> ServiceHandle:
    if _http_ok(f"{ports.frontend_url}/structural-lab"):
        return ServiceHandle(name="dashboard_frontend", process=None, external=True, url=ports.frontend_url)

    runtime_dir = _dashboard_runtime_dir()
    _prepare_frontend_runtime(runtime_dir)
    npm = _ensure_command("npm")
    frontend_command = [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(ports.frontend_port)]
    handle = _launch_process(
        "dashboard_frontend_structural",
        frontend_command,
        cwd=runtime_dir,
        env=_frontend_env(ports.api_url),
        log_dir=log_dir,
    )
    if not _wait_for_http(f"{ports.frontend_url}/structural-lab", timeout_seconds=180):
        raise RuntimeError("Structural lab dashboard frontend did not become ready in time.")
    handle.url = ports.frontend_url
    return handle


def _print_status(services: list[ServiceHandle], log_dir: Path, ports: RuntimePorts) -> None:
    print("\nSTRUCTURAL COMPOUNDING LAB COCKPIT")
    print(f"Frontend runtime: {_dashboard_runtime_dir()}")
    print(f"Logs: {log_dir}")
    print(f"API: {ports.api_url}")
    print(f"Frontend: {ports.frontend_url}/structural-lab")
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
                raise RuntimeError(f"Managed service '{handle.name}' exited with code {handle.process.returncode}.")
        if time.time() - last_heartbeat >= 15.0:
            print(
                f"[{time.strftime('%H:%M:%S')}] structural cockpit healthy | "
                f"frontend={ports.frontend_url}/structural-lab | api={ports.api_url}/health"
            )
            last_heartbeat = time.time()
        time.sleep(2.0)


def main() -> None:
    args = _parse_args()
    ports = RuntimePorts(
        api_port=_choose_port(DEFAULT_API_PORT),
        frontend_port=_choose_port(DEFAULT_FRONTEND_PORT),
    )
    structural_project_root = resolve_structural_lab_project_root()
    log_dir = structural_lab_output_root() / f"structural_cockpit_launcher_{_timestamp()}"
    log_dir.mkdir(parents=True, exist_ok=True)

    services: list[ServiceHandle] = []
    services.append(_start_backend(log_dir, ports))
    services.append(_start_frontend(log_dir, ports))
    target_url = f"{ports.frontend_url}/structural-lab"
    if not args.no_browser:
        _browser_open(target_url)
    print(f"Structural project root: {structural_project_root}")
    _monitor(services, log_dir, ports)


if __name__ == "__main__":
    main()
