"""FastAPI telemetry layer for the live-paper dashboard."""

from __future__ import annotations

import asyncio
from pathlib import Path

import os
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from common.dashboard_telemetry import (
    build_trade_markers,
    _has_live_artifacts,
    latest_live_run,
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
            back_root = cfg.path("backtest", "output_dir")
            if back_root and back_root.exists():
                candidates = [p for p in back_root.iterdir() if p.is_dir()]
                if candidates:
                    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    return candidates[0]
        if normalized_mode in {"paper", "live"}:
            live = latest_live_run(config=cfg)
            if live:
                return live

        back_root = cfg.path("backtest", "output_dir")
        if back_root and back_root.exists():
            candidates = [p for p in back_root.iterdir() if p.is_dir()]
            if candidates:
                candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return candidates[0]
        return None

    # explicit run id: check live output first, then backtest output
    if normalized_mode == "backtest":
        back_root = cfg.path("backtest", "output_dir") / run_id
        if back_root.exists():
            return back_root

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
        back_root = _config().path("backtest", "output_dir")
        candidates = []
        if back_root and back_root.exists():
            for path in sorted(back_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if path.is_dir():
                    candidates.append(
                        {
                            "run_id": path.name,
                            "path": str(path),
                            "has_portfolio_status": (path / "portfolio_status.json").exists(),
                            "last_write_time": path.stat().st_mtime,
                        }
                    )
        return {"runs": candidates}
    return {"runs": list_live_runs(config=_config())}


@app.get("/api/snapshot")
def snapshot(run_id: str = Query("latest"), mode: str = Query("paper")) -> dict:
    run_dir = _resolve_run_dir(run_id, mode)
    return load_live_dashboard_snapshot(run_dir, config=_config())


@app.get("/api/candles")
def candles(
    symbol: str,
    timeframe: str = Query("15m"),
    limit: int = Query(500, ge=50, le=5000),
    run_id: str = Query("latest"),
    mode: str = Query("paper"),
) -> dict:
    payload = load_symbol_candles(
        symbol,
        timeframe=timeframe,
        limit=limit,
        config=_config(),
    )
    run_dir = _resolve_run_dir(run_id, mode)
    snapshot = load_live_dashboard_snapshot(run_dir, config=_config(), trade_limit=2000, signal_limit=0)
    payload["markers"] = build_trade_markers(snapshot["trade_rows"], symbol=symbol)
    return payload


@app.websocket("/ws/live")
async def live_stream(websocket: WebSocket, mode: str = "paper") -> None:
    await websocket.accept()
    last_signature = None
    try:
        while True:
            run_dir = _resolve_run_dir("latest", mode)
            payload = load_live_dashboard_snapshot(run_dir, config=_config())
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
            payload = load_live_dashboard_snapshot(run_dir, config=_config())
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
