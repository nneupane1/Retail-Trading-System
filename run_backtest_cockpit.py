from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

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
    _terminate_process_tree,
    _timestamp,
    _wait_for_http,
)


DEFAULT_PHASE2_RUN = ROOT / "backtest" / "output" / "capital_refactor" / "phase2_capital_lane_experiment" / "scenario_phase2_capital_lane_candidate_full_history"
DEFAULT_BACKTEST_API_PORT = 8102
DEFAULT_BACKTEST_FRONTEND_PORT = 3102


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the backtest replay cockpit.")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open the browser.")
    parser.add_argument(
        "--run-path",
        default=str(DEFAULT_PHASE2_RUN),
        help="Scenario directory to display in backtest mode.",
    )
    return parser.parse_args()


def _frontend_runtime_env(api_url: str) -> dict[str, str]:
    env = _frontend_env(api_url)
    env["NEXT_PUBLIC_DASHBOARD_MODE"] = "backtest"
    return env


def _dashboard_runtime_dir() -> Path:
    return Path.home() / "RetailTradingSystemDashboardRuntime"


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


def _ensure_frontend_build_runtime(runtime_dir: Path, api_url: str) -> None:
    build_id = runtime_dir / ".next" / "BUILD_ID"
    marker = runtime_dir / ".next" / "dashboard_api_url.txt"
    if build_id.exists() and marker.exists():
        try:
            if marker.read_text(encoding="utf-8").strip() == api_url.strip():
                return
        except Exception:
            pass
    npm = _ensure_command("npm")
    _run_checked([npm, "run", "build"], cwd=runtime_dir, env=_frontend_runtime_env(api_url))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(api_url.strip(), encoding="utf-8")


def _backend_runtime_env(run_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DASHBOARD_MODE"] = "backtest"
    env["DASHBOARD_BACKTEST_RUN_PATH"] = str(run_path)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _start_backend(log_dir: Path, ports: RuntimePorts, run_path: Path) -> ServiceHandle:
    if _http_ok(f"{ports.api_url}/health"):
        return ServiceHandle(name="dashboard_api", process=None, external=True, url=ports.api_url)

    _ensure_backend_dependencies()
    handle = _launch_process(
        "dashboard_api_backtest",
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
        env=_backend_runtime_env(run_path),
        log_dir=log_dir,
    )
    if not _wait_for_http(f"{ports.api_url}/health", timeout_seconds=90):
        raise RuntimeError("Backtest dashboard API did not become healthy in time.")
    handle.url = ports.api_url
    return handle


def _start_frontend(log_dir: Path, ports: RuntimePorts) -> ServiceHandle:
    if _http_ok(ports.frontend_url):
        return ServiceHandle(name="dashboard_frontend", process=None, external=True, url=ports.frontend_url)

    runtime_dir = _dashboard_runtime_dir()
    _prepare_frontend_runtime(runtime_dir)
    npm = _ensure_command("npm")
    frontend_command = [npm, "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(ports.frontend_port)]
    startup_timeout = 120
    try:
        _ensure_frontend_build_runtime(runtime_dir, ports.api_url)
    except Exception as exc:
        (log_dir / "dashboard_frontend_backtest.mode.txt").write_text(
            f"frontend_mode=dev_fallback\nreason={exc}\n",
            encoding="utf-8",
        )
        frontend_command = [npm, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", str(ports.frontend_port)]
        startup_timeout = 180
    handle = _launch_process(
        "dashboard_frontend_backtest",
        frontend_command,
        cwd=runtime_dir,
        env=_frontend_runtime_env(ports.api_url),
        log_dir=log_dir,
    )
    if not _wait_for_http(ports.frontend_url, timeout_seconds=startup_timeout):
        raise RuntimeError("Backtest dashboard frontend did not become ready in time.")
    handle.url = ports.frontend_url
    return handle


def _print_status(services: list[ServiceHandle], log_dir: Path, ports: RuntimePorts, run_path: Path) -> None:
    print("\nBACKTEST COCKPIT STATUS")
    print(f"Run path: {run_path}")
    print(f"Frontend runtime: {_dashboard_runtime_dir()}")
    print(f"Logs: {log_dir}")
    print(f"API: {ports.api_url}")
    print(f"Frontend: {ports.frontend_url}/backtest/market")
    for handle in services:
        mode = "external" if handle.external else "managed"
        pid = handle.process.pid if handle.process is not None else "-"
        print(f"- {handle.name}: {mode} | pid={pid} | url={handle.url or '-'}")


def _monitor(services: list[ServiceHandle], log_dir: Path, ports: RuntimePorts, run_path: Path) -> None:
    _print_status(services, log_dir, ports, run_path)
    last_heartbeat = 0.0
    while True:
        for handle in services:
            if handle.process is not None and handle.process.poll() is not None:
                raise RuntimeError(f"Managed service '{handle.name}' exited with code {handle.process.returncode}.")
        if time.time() - last_heartbeat >= 15.0:
            print(
                f"[{time.strftime('%H:%M:%S')}] backtest cockpit healthy | "
                f"frontend={ports.frontend_url}/backtest/market | api={ports.api_url}/health"
            )
            last_heartbeat = time.time()
        time.sleep(2.0)


def main() -> None:
    args = _parse_args()
    run_path = Path(args.run_path).expanduser().resolve()
    if not run_path.exists():
        raise RuntimeError(f"Backtest run path does not exist: {run_path}")

    ports = RuntimePorts(
        api_port=_choose_port(DEFAULT_BACKTEST_API_PORT),
        frontend_port=_choose_port(DEFAULT_BACKTEST_FRONTEND_PORT),
    )
    log_dir = ROOT / "backtest" / "output" / f"backtest_cockpit_launcher_{_timestamp()}"
    log_dir.mkdir(parents=True, exist_ok=True)

    services: list[ServiceHandle] = []
    try:
        services.append(_start_backend(log_dir, ports, run_path))
        services.append(_start_frontend(log_dir, ports))
        target_url = f"{ports.frontend_url}/backtest/market"
        if not args.no_browser:
            _browser_open(target_url)
        _monitor(services, log_dir, ports, run_path)
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    finally:
        for handle in reversed(services):
            if handle.managed:
                _terminate_process_tree(handle.process)


if __name__ == "__main__":
    main()
