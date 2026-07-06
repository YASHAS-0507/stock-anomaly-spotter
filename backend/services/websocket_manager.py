"""
websocket_manager.py
--------------------
Manages WebSocket connections and broadcasts real-time market status updates.
Broadcasts every 5 seconds; heartbeat ping every 30 seconds.
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Set
from fastapi import WebSocket, WebSocketDisconnect


def _get_market_status() -> dict:
    """Compute NSE market status (9:15–15:30 IST, Mon–Fri)."""
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(IST)
    day = now.weekday()  # 0=Mon, 6=Sun
    total = now.hour * 60 + now.minute
    is_open = day < 5 and 555 <= total <= 930  # 9:15=555, 15:30=930
    return {
        "market_status": "OPEN" if is_open else "CLOSED",
        "timestamp_ist": now.strftime("%H:%M:%S"),
    }


def _get_scheduler_snapshot() -> dict:
    """Return a lightweight scheduler status snapshot for WebSocket broadcast."""
    try:
        from scheduler.market_scheduler import market_scheduler
        from broker.auto_paper_broker import auto_broker
        return {
            "running":          market_scheduler.running,
            "watchlist_count":  len(market_scheduler.watchlist),
            "open_positions":   len(auto_broker.positions),
            "daily_pnl":        round(auto_broker.daily_pnl, 2),
        }
    except Exception:
        return {"running": False, "watchlist_count": 0, "open_positions": 0, "daily_pnl": 0.0}


class WebSocketManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._broadcast_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._scheduler_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections.add(websocket)

        # Send current market status immediately on connect
        await self._send_status(websocket)

        # Start background tasks if not running
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        if self._scheduler_task is None or self._scheduler_task.done():
            self._scheduler_task = asyncio.create_task(self._scheduler_broadcast_loop())

    def disconnect(self, websocket: WebSocket):
        self._connections.discard(websocket)

    async def _send_status(self, websocket: WebSocket):
        try:
            payload = {
                "type": "market_status",
                "timestamp": int(time.time() * 1000),
                "data": _get_market_status(),
            }
            await websocket.send_text(json.dumps(payload))
        except Exception:
            pass

    async def _broadcast_loop(self):
        """Broadcast market status to all connected clients every 5 seconds."""
        while self._connections:
            await asyncio.sleep(5)
            if not self._connections:
                break
            dead = set()
            for ws in list(self._connections):
                try:
                    await self._send_status(ws)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def _heartbeat_loop(self):
        """Send a ping every 30 seconds to keep connections alive."""
        while self._connections:
            await asyncio.sleep(30)
            if not self._connections:
                break
            dead = set()
            for ws in list(self._connections):
                try:
                    await ws.send_text(json.dumps({"type": "ping", "timestamp": int(time.time() * 1000)}))
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def _scheduler_broadcast_loop(self):
        """Broadcast scheduler status to all connected clients every 10 seconds."""
        while self._connections:
            await asyncio.sleep(10)
            if not self._connections:
                break
            payload = json.dumps({
                "type":      "scheduler_status",
                "timestamp": int(time.time() * 1000),
                "data":      _get_scheduler_snapshot(),
            })
            dead = set()
            for ws in list(self._connections):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._connections.discard(ws)


websocket_manager = WebSocketManager()
