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


def _resolve_run_dir(run_id: str | None) -> Path | None:
    cfg = _config()
    # If asking for latest, prefer backtest output when the dashboard is configured for backtest.
    if not run_id or run_id == "latest":
        if DASHBOARD_MODE == "backtest":
            back_root = cfg.path("backtest", "output_dir")
            if back_root and back_root.exists():
                candidates = [p for p in back_root.iterdir() if p.is_dir()]
                if candidates:
                    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    return candidates[0]
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
def runs() -> dict:
    return {"runs": list_live_runs(config=_config())}


@app.get("/api/snapshot")
def snapshot(run_id: str = Query("latest")) -> dict:
    run_dir = _resolve_run_dir(run_id)
    return load_live_dashboard_snapshot(run_dir, config=_config())


@app.get("/api/candles")
def candles(
    symbol: str,
    timeframe: str = Query("15m"),
    limit: int = Query(500, ge=50, le=5000),
    run_id: str = Query("latest"),
) -> dict:
    payload = load_symbol_candles(
        symbol,
        timeframe=timeframe,
        limit=limit,
        config=_config(),
    )
    run_dir = _resolve_run_dir(run_id)
    snapshot = load_live_dashboard_snapshot(run_dir, config=_config(), trade_limit=2000, signal_limit=0)
    payload["markers"] = build_trade_markers(snapshot["trade_rows"], symbol=symbol)
    return payload


@app.websocket("/ws/live")
async def live_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    last_signature = None
    try:
        while True:
            run_dir = latest_live_run(config=_config())
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
async def backtest_stream(websocket: WebSocket, run_id: str = "latest") -> None:
    await websocket.accept()
    last_signature = None
    try:
        while True:
            run_dir = _resolve_run_dir(run_id)
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
