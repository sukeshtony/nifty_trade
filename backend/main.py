"""FastAPI main application entry point — Nifty Options Trading Platform."""

import asyncio
import logging
import threading
import time as _time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import get_settings
from database.connection import init_db

# Routers
from routers.market import router as market_router
from routers.signals import router as signals_router
from routers.options import router as options_router
from routers.trades import router as trades_router
from routers.paper_trading import router as paper_trading_router
from routers.ws import (
    router as ws_router,
    set_event_loop,
    broadcast_from_thread,
    make_tick_broadcast_callback,
    manager as ws_manager,
)

# ── Config ──

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate Limiter ──

limiter = Limiter(key_func=get_remote_address)

# ── Graceful shutdown event ──

_stop_event = threading.Event()


# ── Background refresh helpers ─────────────────────────────────────────────────

def _refresh_option_chain():
    """Fetch option chain (ATM ±5), update cache, broadcast to WS clients."""
    from services.market_data_service import market_service
    from services.market_state import market_state_manager
    from services.options_engine import options_engine
    from utils.cache import cache

    # Skip silently when Angel One session is not established — avoids hammering
    # the login endpoint and triggering "Access denied because of exceeding access rate"
    if not market_service._connected:
        return

    chain = market_service.get_option_chain("NIFTY", num_strikes=5)
    if not chain:
        return

    state = market_state_manager.get_state("NIFTY")
    spot = state.get("current_price", 0)
    if not spot:
        ltp_data = market_service.get_ltp("NIFTY")
        spot = ltp_data.get("ltp", 0) if ltp_data else 0

    # Store full analysis in cache (used by REST /options/analysis)
    analysis = options_engine.analyze(chain, spot)
    cache.set("options_analysis:NIFTY", analysis, ttl=15)

    # Broadcast live option chain to all connected browsers
    broadcast_from_thread({
        "type":              "option_chain",
        "spot_price":        spot,
        "data":              chain,
        "pcr":               analysis.get("pcr", 0),
        "pcr_interpretation": analysis.get("pcr_interpretation", ""),
        "max_pain":          analysis.get("max_pain"),
        "oi_support":        analysis.get("oi_support"),
        "oi_resistance":     analysis.get("oi_resistance"),
        "dominant_buildup":  analysis.get("dominant_buildup", "NONE"),
    })


def _refresh_candles():
    """Refresh 1-minute candle data and re-seed market state indicators."""
    from services.market_data_service import market_service
    from services.market_state import market_state_manager
    from utils.cache import cache

    if not market_service._connected:
        return

    candles = market_service.get_candle_data("NIFTY", interval="ONE_MINUTE")
    if candles:
        cache.set("candles:NIFTY:ONE_MINUTE", candles, ttl=120)
        market_state_manager.initialize_from_history("NIFTY", candles)

    market_service.get_full_market_data("NIFTY")


# ── Background periodic refresh thread ────────────────────────────────────────

def _periodic_refresh():
    """
    Tiered refresh:
      every 10 s  — option chain (LTPs for paper trading + WS broadcast)
      every 60 s  — candles + full market data (indicators)
    """
    tick = 0
    _stop_event.wait(5)  # give WebSocket thread time to connect first

    while not _stop_event.is_set():
        tick += 1
        try:
            _refresh_option_chain()            # every 10 s
        except Exception as e:
            logger.error(f"Option chain refresh error: {e}")

        if tick % 6 == 0:                      # every 60 s
            try:
                _refresh_candles()
            except Exception as e:
                logger.error(f"Candle refresh error: {e}")

        _stop_event.wait(10)                   # interruptible sleep


# ── WebSocket startup thread ───────────────────────────────────────────────────

def _background_startup():
    """Login to Angel One and start the SmartWebSocketV2 connection."""
    from services.market_data_service import market_service
    try:
        market_service.start_websocket()
    except Exception as e:
        logger.error(f"Background startup error: {e}")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Nifty Trading Platform...")
    init_db()
    logger.info("Database tables ready")

    # 1. Capture the asyncio event loop — needed for thread→async broadcasts
    loop = asyncio.get_event_loop()
    set_event_loop(loop)

    # 2. Register tick broadcast callback on market state manager
    from services.market_state import market_state_manager
    market_state_manager.register_callback(make_tick_broadcast_callback())

    # 3. Start Angel One WebSocket in background thread
    threading.Thread(target=_background_startup, daemon=True).start()

    # 4. Start tiered background refresh thread
    threading.Thread(target=_periodic_refresh, daemon=True).start()

    yield

    # ── Shutdown ──
    logger.info("Shutting down Nifty Trading Platform...")
    _stop_event.set()
    from services.market_data_service import market_service
    market_service.stop_websocket()


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nifty Options Trading API",
    description=(
        "Logic-based Nifty options trading decision platform — "
        "real-time price, BUY CE/PE/NO TRADE signals, "
        "option chain analytics, and trade tracking."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter


# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = _time.time()
    response = await call_next(request)
    ms = (_time.time() - start) * 1000
    logger.info(
        f"{'OK' if response.status_code < 400 else 'ERR'} "
        f"{request.method} {request.url.path} "
        f"{response.status_code} | {ms:.1f}ms"
    )
    return response


# ── Mount Routers ──────────────────────────────────────────────────────────────

app.include_router(ws_router)           # WebSocket at /ws
app.include_router(market_router)
app.include_router(signals_router)
app.include_router(options_router)
app.include_router(trades_router)
app.include_router(paper_trading_router)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "app": "Nifty Options Trading API",
        "version": "1.0.0",
        "status": "running",
        "ws_clients": len(ws_manager.connections),
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "ws_clients": len(ws_manager.connections)}
