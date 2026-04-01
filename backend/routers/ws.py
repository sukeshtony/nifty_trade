"""WebSocket router — pushes live market ticks and option chain to all connected browsers.

Architecture:
    Angel One WS tick → market_state_manager.update_tick() → broadcast_from_thread()
        → asyncio.run_coroutine_threadsafe → manager.broadcast() → every browser client

Message types sent to frontend:
    { "type": "tick",         price, change, change_pct, ema_9, ema_21, vwap,
                              momentum, atr, session_high, session_low, trend }

    { "type": "option_chain", spot_price, data: [...strikes], pcr,
                              max_pain, oi_support, oi_resistance, dominant_buildup }
"""

import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

# ── Event loop reference (set once from lifespan, used by background threads) ──
_event_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


def broadcast_from_thread(msg: dict) -> None:
    """Thread-safe broadcast — safe to call from ANY background thread.
    Schedules the async broadcast on the FastAPI event loop.
    """
    if _event_loop is None or not manager.connections:
        return
    asyncio.run_coroutine_threadsafe(manager.broadcast(msg), _event_loop)


# ── Connection manager ──

class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.add(ws)
        logger.info(f"WS client connected — total: {len(self.connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws)
        logger.info(f"WS client disconnected — total: {len(self.connections)}")

    async def broadcast(self, msg: dict) -> None:
        """Send msg to all connected clients; silently drop dead connections."""
        if not self.connections:
            return
        dead: set[WebSocket] = set()
        for ws in list(self.connections):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.connections.discard(ws)


manager = ConnectionManager()


# ── Callback registered on market_state_manager ──

def make_tick_broadcast_callback():
    """Returns a callback to register with market_state_manager.register_callback().
    Called from the Angel One WebSocket thread on every price tick.
    """
    def _on_tick(symbol: str, state: dict) -> None:
        if symbol != "NIFTY":
            return
        msg = {
            "type":         "tick",
            "price":        state.get("current_price", 0),
            "change":       state.get("change", 0),
            "change_pct":   state.get("change_pct", 0),
            "ema_9":        state.get("ema_9"),
            "ema_21":       state.get("ema_21"),
            "vwap":         state.get("vwap"),
            "momentum":     state.get("momentum", 0),
            "atr":          state.get("atr"),
            "session_high": state.get("session_high", 0),
            "session_low":  state.get("session_low", 0),
            "trend":        state.get("trend", {}),
        }
        broadcast_from_thread(msg)
    return _on_tick


# ── WebSocket endpoint ──

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; client may send ping text frames
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
