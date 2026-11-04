#!/usr/bin/env python3
"""
CHAOS ENGINE HFT - Backend API (FastAPI)

Provides REST API endpoints for:
- Robot status and control
- Account and position monitoring
- Order management
- Configuration
- Metrics and statistics
- Logging and alerts
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
import uvicorn
import logging
import json
import time
from enum import Enum
from pathlib import Path

# API configuration is intentionally independent from the trading engine's dataclass config.
class APIConfig:
    def __init__(self):
        self._config = {
            "environment": "demo",
            "account_mode": "AUTO",
            "broker": {"symbol": "EURUSDm"},
            "trading": {"allow_buy": True, "allow_sell": True},
            "risk": {
                "max_daily_loss_percent": 2,
                "max_drawdown_percent": 8,
                "max_margin_utilization_percent": 20,
            },
        }

    def get(self, key, default=None):
        value = self._config
        for part in key.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def get_bool(self, key, default=False):
        return bool(self.get(key, default))

    def get_config(self):
        return self._config

_api_config = APIConfig()

def get_config():
    return _api_config

def init_config():
    return _api_config

class IPCBridge:
    """Optional bridge: the demo API remains usable without MetaTrader IPC."""
    def connect(self):
        return False

    def is_connected(self):
        return False

# Initialize configuration
init_config()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chaos_engine_hft.api")

# Create FastAPI app
app = FastAPI(
    title="CHAOS ENGINE HFT API",
    description="REST API for CHAOS ENGINE HFT trading system",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)

# Global state
startup_time = time.time()
shutdown_requested = False


# ============================================================
# Enums and Models
# ============================================================

class Environment(str, Enum):
    DEMO = "demo"
    LIVE = "live"
    PAPER = "paper"


class AccountMode(str, Enum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class TradingState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class RegimeType(str, Enum):
    CALM = "CALM"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    CRITICAL = "CRITICAL"


# Request/Response Models

class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: float = Field(default_factory=time.time)
    uptime_seconds: float = Field(default_factory=lambda: time.time() - startup_time)
    version: str = "0.1.0"


class StatusResponse(BaseModel):
    """General status response."""
    state: TradingState
    environment: Environment
    account_mode: AccountMode
    symbol: str = "EURUSDm"
    connected: bool = False


class AccountInfo(BaseModel):
    """Account information."""
    balance: float
    equity: float
    margin_used: float
    margin_free: float
    margin_utilization: float = Field(alias="marginUtilization")
    daily_pnl: float = 0.0
    daily_return_pct: float = 0.0


class PositionInfo(BaseModel):
    """Position information for a symbol."""
    symbol: str
    volume: float = 0.0
    net_volume: float = 0.0
    avg_price: float = 0.0
    swaps: float = 0.0
    commission: float = 0.0
    profit: float = 0.0
    commission_paid: float = 0.0


class OrderRequest(BaseModel):
    """Order request for placement."""
    symbol: str = "EURUSDm"
    order_type: OrderType
    volume: float = Field(gt=0)
    price: Optional[float] = None
    comment: str = "hft_scalper_demo"
    magic: int = 860001
    
    @validator("volume")
    def volume_must_be_reasonable(cls, v):
        if v > 100.0:
            raise ValueError("Volume too large for standard lot sizes")
        return v


class OrderResponse(BaseModel):
    """Order placement response."""
    ticket: int = 0
    status: OrderStatus = OrderStatus.PENDING
    symbol: str
    volume: float
    price: float
    comment: str
    magic: int
    request_time: float = Field(default_factory=time.time)


class ConfigUpdate(BaseModel):
    """Configuration update request."""
    key: str
    value: Any
    
    @validator("*")
    def validate_key_exists(cls, v, values):
        # Will be validated in handler
        return v


# ============================================================
# Startup/Shutdown
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("CHAOS ENGINE HFT API starting up...")
    
    # Initialize optional IPC bridge
    ipc = IPCBridge()
    if not ipc.connect():
        logger.warning("IPC bridge connection failed on startup")
    
    logger.info("CHAOS ENGINE HFT API startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("CHAOS ENGINE HFT API shutting down...")
    shutdown_requested = True


# ============================================================
# Endpoints
# ============================================================

@app.get("/health", response_model=HealthCheck, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthCheck()


@app.get("/api/v1/status", response_model=StatusResponse, tags=["System"])
async def get_status(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get robot status."""
    # In production, validate credentials
    config = get_config()
    
    # Determine state based on config
    env = Environment(config.get("environment", "demo"))
    mode = AccountMode(config.get("account_mode", "AUTO"))
    
    # Check if trading is allowed
    allow_buy = config.get_bool("trading.allow_buy", True)
    allow_sell = config.get_bool("trading.allow_sell", True)
    
    # Check IPC connection
    ipc_connected = False
    try:
        ipc = IPCBridge()
        ipc_connected = ipc.is_connected()
    except Exception:
        pass
    
    state = TradingState.RUNNING if (ipc_connected and allow_buy and allow_sell) else TradingState.STOPPED
    
    return StatusResponse(
        state=state,
        environment=env,
        account_mode=mode,
        symbol=config.get("broker.symbol", "EURUSDm"),
        connected=ipc_connected,
    )


@app.get("/api/v1/account", tags=["Account"])
async def get_account(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get account information."""
    # In production, validate credentials and fetch from broker
    # For now, return mock data based on config
    config = get_config()
    
    # Check environment
    env = config.get("environment", "demo")
    
    if env == "demo" or env == "paper":
        # Return demo account info
        return AccountInfo(
            balance=10000.0,
            equity=10000.0,
            margin_used=0.0,
            margin_free=10000.0,
            margin_utilization=0.0,
            daily_pnl=0.0,
            daily_return_pct=0.0,
        )
    else:
        # Live would connect to real broker
        raise HTTPException(status_code=503, detail="Live account not accessible via API")


@app.get("/api/v1/positions", response_model=List[PositionInfo], tags=["Account"])
async def get_positions(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get open positions."""
    config = get_config()
    env = config.get("environment", "demo")
    
    if env in ("demo", "paper"):
        # Return empty positions for demo
        return []
    else:
        raise HTTPException(status_code=503, detail="Live positions not accessible via API")


@app.get("/api/v1/orders", tags=["Orders"])
async def get_orders(
    status: Optional[OrderStatus] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get orders."""
    # Return mock/order history
    config = get_config()
    env = config.get("environment", "demo")
    
    if env not in ("demo", "paper"):
        raise HTTPException(status_code=503, detail="Live orders not accessible via API")
    
    # Mock order history
    return [
        {
            "ticket": 123456,
            "status": OrderStatus.FILLED,
            "symbol": "EURUSDm",
            "volume": 0.1,
            "price": 1.1178,
            "comment": "hft_scalper_demo",
            "magic": 860001,
            "request_time": time.time() - 300,
        },
        {
            "ticket": 123457,
            "status": OrderStatus.CANCELLED,
            "symbol": "EURUSDm",
            "volume": 0.05,
            "price": 1.1185,
            "comment": "hft_scalper_demo",
            "magic": 860001,
            "request_time": time.time() - 600,
        },
    ]


@app.post("/api/v1/bot/start", tags=["Bot Control"])
async def start_bot(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Start the trading bot."""
    config = get_config()
    env = config.get("environment", "demo")
    
    if env != "demo":
        raise HTTPException(status_code=403, detail="Live trading must be explicitly authorized")
    
    # In production, would start the MQL5 Expert Advisor
    # and/or the Python Quant Engine
    logger.info("Bot start requested (demo mode)")
    
    return {
        "status": "started",
        "mode": "demo",
        "message": "Bot started in demo mode - no real trading",
        "timestamp": time.time(),
    }


@app.post("/api/v1/bot/stop", tags=["Bot Control"])
async def stop_bot(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Stop the trading bot."""
    logger.info("Bot stop requested")
    
    return {
        "status": "stopped",
        "message": "Bot stopped",
        "timestamp": time.time(),
    }


@app.post("/api/v1/bot/pause", tags=["Bot Control"])
async def pause_bot(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Pause the trading bot."""
    return {
        "status": "paused",
        "message": "Bot paused",
        "timestamp": time.time(),
    }


@app.get("/api/v1/config", tags=["Configuration"])
async def get_config_endpoint(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get current configuration."""
    config = get_config()
    return config.get_config()


@app.post("/api/v1/config", tags=["Configuration"])
async def update_config(
    request: ConfigUpdate,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Update configuration value."""
    config = get_config()
    
    # Validate key exists in config
    # In production, would have proper validation
    key = request.key
    value = request.value
    
    # Set the value
    try:
        # Navigate to nested key
        keys = key.split(".")
        current = config._config
        for k in keys[:-1]:
            if k not in current:
                raise HTTPException(status_code=400, detail=f"Config key path not found: {key}")
            current = current[k]
        current[keys[-1]] = value
        
        # Save config
        config_path = Path(__file__).parent.parent / "config" / "default.yaml"
        # Note: In production, would properly save and validate
        
        return {"status": "updated", "key": key, "value": value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/symbols", tags=["Symbols"])
async def get_symbols(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get available symbols."""
    config = get_config()
    symbol = config.get("broker.symbol", "EURUSDm")
    
    # In production, would query broker for available symbols
    return {
        "symbols": [
            {"symbol": "EURUSDm", "description": "EUR/USD micro"},
            {"symbol": "GBPUSDm", "description": "GBP/USD micro"},
            {"symbol": "USDJPYm", "description": "USD/JPY micro"},
            {"symbol": "XAUUSD", "description": "Gold/USD"},
            {"symbol": "XAGUSD", "description": "Silver/USD"},
        ],
        "selected": symbol,
    }


@app.get("/api/v1/metrics", tags=["Metrics"])
async def get_metrics(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get performance metrics."""
    # In production, would fetch from database
    # For now, return structured metrics
    return {
        "total_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "calmar_ratio": 0.0,
        "total_cotations": 0,
        "total_rejections": 0,
        "acceptances": 0,
        "slippage_total": 0.0,
    }


@app.get("/api/v1/risk", tags=["Risk"])
async def get_risk_status(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get risk status."""
    config = get_config()
    
    risk_config = config.get("risk", {})
    
    # Calculate current risk metrics (simulated)
    daily_loss_pct = risk_config.get("max_daily_loss_percent", 2)
    max_dd = risk_config.get("max_drawdown_percent", 8)
    margin_util = risk_config.get("max_margin_utilization_percent", 20)
    
    return {
        "max_daily_loss_pct": daily_loss_pct,
        "max_drawdown_pct": max_dd,
        "max_margin_utilization_pct": margin_util,
        "current_daily_pnl_pct": 0.0,  # Would be calculated from actual PnL
        "current_margin_utilization_pct": 0.0,
        "daily_loss_triggered": False,
        "drawdown_warning_triggered": False,
        "hard_drawdown_stopped": False,
    }


@app.get("/api/v1/logs", tags=["Logs"])
async def get_logs(
    limit: int = 100,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get recent logs."""
    # In production, would read from log files
    # For now, return mock structure
    return {
        "logs": [
            {
                "timestamp": time.time() - i * 60,
                "level": "INFO" if i % 2 == 0 else "DEBUG",
                "message": f"Sample log entry {i}",
                "component": "api",
            }
            for i in range(min(limit, 10))
        ],
        "total_returned": min(limit, 10),
    }


# ============================================================
# Authentication (placeholder)
# ============================================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Get current authenticated user."""
    # Placeholder - in production would validate JWT tokens
    return {"username": "admin", "role": "trader"}


# ============================================================
# Main
# ============================================================

def main():
    """Run the FastAPI application."""
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
