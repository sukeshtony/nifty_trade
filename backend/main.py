"""FastAPI main application entry point — Nifty Options Trading Platform."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import time

from config import get_settings
from database.connection import init_db

# Routers
from routers.market import router as market_router
from routers.signals import router as signals_router
from routers.options import router as options_router
from routers.trades import router as trades_router
from routers.paper_trading import router as paper_trading_router

# ── Config ──

settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Rate Limiter ──

limiter = Limiter(key_func=get_remote_address)


# ── Lifespan ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    logger.info("🚀 Starting Nifty Trading Platform...")
    init_db()
    logger.info("✅ Database tables created")

    # Start WebSocket + background data fetching in a separate thread
    from services.market_data_service import market_service
    import threading

    def _background_startup():
        """Handle Angel One login and WebSocket in background."""
        try:
            market_service.start_websocket()
        except Exception as e:
            logger.error(f"Background startup error: {e}")

    threading.Thread(target=_background_startup, daemon=True).start()

    # Background periodic data refresh (candles, option chain)
    def _periodic_refresh():
        """Refresh candle data and option chain every 60 seconds."""
        import time as t
        from services.indicator_engine import compute_all_indicators
        from services.options_engine import options_engine
        from services.market_state import market_state_manager
        from utils.cache import cache

        # Give WebSocket thread head-start to establish initial connection
        t.sleep(5)

        while True:
            try:
                # Refresh candle data
                candles = market_service.get_candle_data("NIFTY", interval="ONE_MINUTE")
                if candles:
                    cache.set("candles:NIFTY:ONE_MINUTE", candles, ttl=120)

                # Refresh full market data
                market_service.get_full_market_data("NIFTY")

                # Refresh option chain
                chain = market_service.get_option_chain("NIFTY", num_strikes=3)
                if chain:
                    state = market_state_manager.get_state("NIFTY")
                    spot = state.get("current_price", 0)
                    if spot:
                        analysis = options_engine.analyze(chain, spot)
                        cache.set("options_analysis:NIFTY", analysis, ttl=60)

            except Exception as e:
                logger.error(f"Periodic refresh error: {e}")

            t.sleep(60)

    threading.Thread(target=_periodic_refresh, daemon=True).start()

    yield

    logger.info("👋 Shutting down Nifty Trading Platform...")
    from services.market_data_service import market_service
    market_service.stop_websocket()


# ── App ──

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


# ── Middleware ──

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
    logger.error(f"❌ Unhandled Exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    logger.info(
        f"{'✅' if response.status_code < 400 else '⚠️'} "
        f"{request.method} {request.url.path} "
        f"{response.status_code} | {process_time:.1f}ms"
    )
    return response


# ── Mount Routers ──

app.include_router(market_router)
app.include_router(signals_router)
app.include_router(options_router)
app.include_router(trades_router)
app.include_router(paper_trading_router)


# ── Health ──

@app.get("/", tags=["Health"])
def root():
    return {
        "app": "Nifty Options Trading API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
