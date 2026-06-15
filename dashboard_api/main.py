"""FastAPI telemetry layer for the live-paper dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path

import os
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from common.dashboard_telemetry import (
    _has_live_artifacts,
    latest_live_run,
    list_backtest_runs,
    list_live_runs,
    load_live_dashboard_snapshot,
    load_symbol_candles,
)
from config import AppConfig


app = FastAPI(
    title="Retail Trading Dashboard API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _config() -> AppConfig:
    return AppConfig.load()


DASHBOARD_MODE = os.environ.get("DASHBOARD_MODE", "live").lower()
DASHBOARD_BACKTEST_RUN_PATH = os.environ.get("DASHBOARD_BACKTEST_RUN_PATH")


def _normalize_mode(mode: str | None) -> str:
    normalized = str(mode or DASHBOARD_MODE or "paper").lower()
    if normalized == "backtest":
        return "backtest"
    if normalized == "live":
        return "live"
    return "paper"


def _resolve_run_dir(run_id: str | None, mode: str | None = None) -> Path | None:
    cfg = _config()
    normalized_mode = _normalize_mode(mode)
    # If asking for latest, prefer backtest output when the dashboard is configured for backtest.
    if not run_id or run_id == "latest":
        if normalized_mode == "backtest":
            if DASHBOARD_BACKTEST_RUN_PATH:
                env_path = Path(DASHBOARD_BACKTEST_RUN_PATH)
                if env_path.exists():
                    return env_path
            candidates = list_backtest_runs(config=cfg)
            if candidates:
                return Path(candidates[0]["path"])
        if normalized_mode in {"paper", "live"}:
            live = latest_live_run(config=cfg)
            if live:
                return live

        candidates = list_backtest_runs(config=cfg)
        if candidates:
            return Path(candidates[0]["path"])
        return None

    # explicit run id: check live output first, then backtest output
    if normalized_mode == "backtest":
        for row in list_backtest_runs(config=cfg):
            if row["run_id"] == run_id:
                return Path(row["path"])

    live_root = cfg.path("live_sim", "output_dir") / run_id
    if live_root.exists() and _has_live_artifacts(live_root):
        return live_root

    live_output_root = cfg.path("live_sim", "output_dir")
    if live_output_root.exists() and _has_live_artifacts(live_output_root):
        return live_output_root

    back_root = cfg.path("backtest", "output_dir") / run_id
    if back_root.exists():
        return back_root

    return None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/runs")
def runs(mode: str = Query("paper")) -> dict:
    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "backtest":
        return {"runs": list_backtest_runs(config=_config())}
    return {"runs": list_live_runs(config=_config())}


@app.get("/api/snapshot")
def snapshot(run_id: str = Query("latest"), mode: str = Query("paper")) -> dict:
    run_dir = _resolve_run_dir(run_id, mode)
    return load_live_dashboard_snapshot(run_dir, config=_config(), mode=mode)


@app.get("/api/candles")
def candles(
    symbol: str,
    timeframe: str = Query("15m"),
    limit: int = Query(500, ge=50, le=5000),
    run_id: str = Query("latest"),
    mode: str = Query("paper"),
    until_time: str | None = Query(None),
) -> dict:
    run_dir = _resolve_run_dir(run_id, mode)
    return load_symbol_candles(
        symbol,
        timeframe=timeframe,
        limit=limit,
        config=_config(),
        run_dir=run_dir,
        mode=mode,
        until_time=until_time,
    )


@app.websocket("/ws/live")
async def live_stream(websocket: WebSocket, mode: str = "paper") -> None:
    await websocket.accept()
    last_signature = None
    try:
        while True:
            run_dir = _resolve_run_dir("latest", mode)
            payload = load_live_dashboard_snapshot(run_dir, config=_config(), mode=mode)
            signature = (
                payload.get("run", {}).get("run_id"),
                payload.get("portfolio_status", {}).get("equity"),
                payload.get("latest_trade", {}).get("exit_time") if payload.get("latest_trade") else None,
                payload.get("latest_signal", {}).get("timestamp") if payload.get("latest_signal") else None,
                payload.get("engine_heartbeat", {}).get("cycle_count"),
                payload.get("engine_heartbeat", {}).get("cycle_completed_at"),
                payload.get("engine_heartbeat", {}).get("status"),
            )
            if signature != last_signature:
                await websocket.send_json(payload)
                last_signature = signature
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/backtest")
async def backtest_stream(websocket: WebSocket, run_id: str = "latest", mode: str = "backtest") -> None:
    await websocket.accept()
    last_signature = None
    try:
        while True:
            run_dir = _resolve_run_dir(run_id, mode)
            payload = load_live_dashboard_snapshot(run_dir, config=_config(), mode=mode)
            signature = (
                payload.get("run", {}).get("run_id"),
                payload.get("portfolio_status", {}).get("equity"),
                payload.get("latest_trade", {}).get("exit_time") if payload.get("latest_trade") else None,
                payload.get("latest_signal", {}).get("timestamp") if payload.get("latest_signal") else None,
                payload.get("engine_heartbeat", {}).get("cycle_count"),
                payload.get("engine_heartbeat", {}).get("cycle_completed_at"),
                payload.get("engine_heartbeat", {}).get("status"),
                payload.get("replay_checkpoint", {}).get("next_index"),
            )
            if signature != last_signature:
                await websocket.send_json(payload)
                last_signature = signature
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        return
