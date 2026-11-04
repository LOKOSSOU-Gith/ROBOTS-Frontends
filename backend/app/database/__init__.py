#!/usr/bin/env python3
"""
CHAOS ENGINE HFT - Database Module

PostgreSQL database models and migrations for the CHAOS ENGINE HFT system.
Tables as specified in the architecture document (Section 16).

 Uses SQLAlchemy 2.0 style with async support.
"""

from __future__ import annotations

from sqlalchemy import (
    create_engine, Table, Column, MetaData, Type,
    String, Float, Integer, Boolean, DateTime, 
    Text, JSON, Index, UniqueConstraint, LargeBinary
)
from sqlalchemy.dialects.postgresql import (
    UUID, JSONB, ARRAY, INTEGER, VARCHAR, TIMESTAMP, BIGINT
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, relationship
from sqlalchemy import select, insert, update, delete
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Any, Dict
import logging

logger = logging.getLogger("chaos_engine_hft.database")

# Base class for ORM models
Base = declarative_base()

# Database configuration
DEFAULT_ASYNC_DATABASE_URL = "postgresql+asyncpg://localhost/chaos_engine_hft"
DEFAULT_SYNC_DATABASE_URL = "postgresql://localhost/chaos_engine_hft"

# Create engines
async_engine = create_engine(DEFAULT_ASYNC_DATABASE_URL)
sync_engine = create_engine(DEFAULT_SYNC_DATABASE_URL)


# ============================================================
# Database Models
# ============================================================

# Accounts table
class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("id", name="uq_accounts_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    broker_name = mapped_column(String(64), nullable=False)
    server_name = mapped_column(String(128))
    account_name = mapped_column(String(64), nullable=False)
    account_mode = mapped_column(String(32), nullable=False)  # hedging, netting, both
    leverage = mapped_column(Integer, nullable=False)
    currency = mapped_column(String(16), nullable=False, default="USD")
    balance = mapped_column(Float, nullable=False, default=10000.0)
    equity = mapped_column(Float, nullable=False, default=10000.0)
    margin_used = mapped_column(Float, nullable=False, default=0.0)
    margin_free = mapped_column(Float, nullable=False, default=10000.0)
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))
    updated_at = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc), 
        onupdate=datetime.now(timezone.utc)
    )
    
    # Relationships
    symbols = relationship("Symbol", back_populates="account")
    positions = relationship("Position", back_populates="account")
    orders = relationship("Order", back_populates="account")
    executions = relationship("Execution", back_populates="account")
    risk_events = relationship("RiskEvent", back_populates="account")


# Brokers table
class Broker(Base):
    __tablename__ = "brokers"
    __table_args__ = (
        UniqueConstraint("id", name="uq_brokers_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    name = mapped_column(String(64), nullable=False)
    server = mapped_column(String(128), nullable=False)
    description = mapped_column(Text, nullable=True)
    is_active = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))
    updated_at = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc), 
        onupdate=datetime.now(timezone.utc)
    )
    
    # Relationships
    accounts = relationship("Account", back_populates="broker")
    symbol_configs = relationship("SymbolConfig", back_populates="broker")


# Symbols table
class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        UniqueConstraint("symbol", "account_id", name="uq_symbols_symbol_account"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    symbol = mapped_column(String(32), nullable=False)  # e.g., EURUSDm
    description = mapped_column(String(128), nullable=True)
    point_value = mapped_column(Float, nullable=False, default=1.0)
    tick_size = mapped_column(Float, nullable=False)
    trade_mode = mapped_column(String(32), nullable=False)  # hedging, netting, both
    margin_mode = mapped_column(String(32), nullable=False)  # retail_hedging, retail_netting, exchange
    max_lot = mapped_column(Float, nullable=False, default=100.0)
    min_lot = mapped_column(Float, nullable=False, default=0.01)
    lot_step = mapped_column(Float, nullable=False, default=0.01)
    spread_mode = mapped_column(String(32), nullable=False, default="variable")
    filling_mode = mapped_column(String(16), nullable=False, default="return")  # FOK, IOC, RETURN, BOC
    volume_min = mapped_column(Float, nullable=False, default=0.01)
    volume_max = mapped_column(Float, nullable=False, default=10.0)
    tick_value = mapped_column(Float, nullable=False, default=1.0)
    swaps_long = mapped_column(Float, nullable=False, default=0.0)
    swaps_short = mapped_column(Float, nullable=False, default=0.0)
    commission = mapped_column(Float, nullable=False, default=0.0)
    account_id = mapped_column(String(128), nullable=False)
    
    # Relationships
    account = relationship("Account", back_populates="symbols")
    price_history = relationship("PriceHistory", back_populates="symbol")
    orders = relationship("Order", back_populates="symbol")


# Symbol configuration overrides
class SymbolConfig(Base):
    __tablename__ = "symbol_configs"
    __table_args__ = (
        UniqueConstraint("symbol", "account_id", name="uq_symbol_configs_symbol_account"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    symbol = mapped_column(String(32), nullable=False)
    account_id = mapped_column(String(128), nullable=False)
    max_spread_points = mapped_column(Integer, nullable=False, default=20)
    max_inv_lots = mapped_column(Float, nullable=False, default=3.0)
    min_volatility_pct = mapped_column(Float, nullable=False, default=0.0001)
    max_volatility_pct = mapped_column(Float, nullable=False, default=5.0)
    inner_spread_points = mapped_column(Integer, nullable=False, default=8)
    risk_per_trade = mapped_column(Float, nullable=False, default=0.02)
    max_trades_per_day = mapped_column(Integer, nullable=False, default=30)
    exit_timeout_bars = mapped_column(Integer, nullable=False, default=30)
    allow_real_trading = mapped_column(Boolean, nullable=False, default=False)
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))
    updated_at = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc), 
        onupdate=datetime.now(timezone.utc)
    )
    
    # Relationships
    account = relationship("Account", back_populates="symbol_configs")


# Bot instances table
class BotInstance(Base):
    __tablename__ = "bot_instances"
    __table_args__ = (
        UniqueConstraint("id", name="uq_bot_instances_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    name = mapped_column(String(64), nullable=False)
    status = mapped_column(String(32), nullable=False, default="stopped")
    environment = mapped_column(String(32), nullable=False, default="demo")
    symbol = mapped_column(String(32), nullable=False, default="EURUSDm")
    mql5_expert_path = mapped_column(String(256), nullable=True)
    python_script_path = mapped_column(String(256), nullable=True)
    config_path = mapped_column(String(256), nullable=True)
    host_node = mapped_column(String(128), nullable=True)  # VPS hostname
    port = mapped_column(Integer, nullable=False, default=8000)
    pid = mapped_column(Integer, nullable=True)  # Process ID
    connected = mapped_column(Boolean, nullable=False, default=False)
    last_tick = mapped_column(DateTime, nullable=True)
    started_at = mapped_column(DateTime, nullable=True)
    stopped_at = mapped_column(DateTime, nullable=True)
    uptime_seconds = mapped_column(Integer, nullable=False, default=0)
    restarts = mapped_column(Integer, nullable=False, default=0)
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))
    updated_at = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc), 
        onupdate=datetime.now(timezone.utc)
    )
    
    # Relationships
    positions = relationship("Position", back_populates="bot_instance")
    orders = relationship("Order", back_populates="bot_instance")
    metrics = relationship("PerformanceSnapshot", back_populates="bot_instance")


# Positions table
class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("id", name="uq_positions_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    bot_instance_id = mapped_column(String(128), nullable=False)
    symbol = mapped_column(String(32), nullable=False)
    account_id = mapped_column(String(128), nullable=False)
    
    # Position details
    volume = mapped_column(Float, nullable=False, default=0.0)  # Net volume
    long_volume = mapped_column(Float, nullable=False, default=0.0)  # Gross long
    short_volume = mapped_column(Float, nullable=False, default=0.0)  # Gross short
    open_price = mapped_column(Float, nullable=True)
    current_price = mapped_column(Float, nullable=True)
    swap_long = mapped_column(Float, nullable=False, default=0.0)
    swap_short = mapped_column(Float, nullable=False, default=0.0)
    commission = mapped_column(Float, nullable=False, default=0.0)
    profit = mapped_column(Float, nullable=False, default=0.0)
    commission_paid = mapped_column(Float, nullable=False, default=0.0)
    
    # Risk tracking
    margin_used = mapped_column(Float, nullable=False, default=0.0)
    swaps = mapped_column(Float, nullable=False, default=0.0)
    
    # Timing
    opened_at = mapped_column(DateTime, nullable=False)
    modified_at = mapped_column(
        DateTime, 
        default=datetime.now(timezone.utc), 
        onupdate=datetime.now(timezone.utc)
    )
    closed_at = mapped_column(DateTime, nullable=True)
    
    # Relationships
    bot_instance = relationship("BotInstance", back_populates="positions")
    account = relationship("Account", back_populates="positions")
    orders = relationship("Order", back_populates="position")


# Orders table
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("id", name="uq_orders_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    bot_instance_id = mapped_column(String(128), nullable=False)
    symbol = mapped_column(String(32), nullable=False)
    account_id = mapped_column(String(128), nullable=False)
    
    # Order details
    ticket = mapped_column(Integer, nullable=False, unique=True)
    order_type = mapped_column(String(16), nullable=False)  # BUY, SELL, BUY_LIMIT, etc.
    volume = mapped_column(Float, nullable=False)
    price = mapped_column(Float, nullable=True)  # Limit price, or 0 for market
    command = mapped_column(String(32), nullable=False, default="ordersend")
    status = mapped_column(String(32), nullable=False, default="pending")
    request_time = mapped_column(DateTime, default=datetime.now(timezone.utc))
    execution_time = mapped_column(DateTime, nullable=True)
    
    # Fill information
    filled_price = mapped_column(Float, nullable=True)
    filled_volume = mapped_column(Float, nullable=False, default=0.0)
    partial_fill = mapped_column(Boolean, nullable=False, default=False)
    
    # PnL
    pnl = mapped_column(Float, nullable=False, default=0.0)
    commission = mapped_column(Float, nullable=False, default=0.0)
    swap = mapped_column(Float, nullable=False, default=0.0)
    
    # Runtime state
    is_active = mapped_column(Boolean, nullable=False, default=True)
    
    # Relationships
    account = relationship("Account", back_populates="orders")
    symbol_rel = relationship("Symbol", back_populates="orders", foreign_keys=[symbol])
    bot_instance = relationship("BotInstance", back_populates="orders")


# Executions table
class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("id", name="uq_executions_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    order_id = mapped_column(String(128), nullable=False)
    symbol = mapped_column(String(32), nullable=False)
    account_id = mapped_column(String(128), nullable=False)
    
    # Execution details
    ticket = mapped_column(Integer, nullable=False)
    execution_type = mapped_column(String(32), nullable=False)  # ordersend, ordermodify
    execution_time = mapped_column(DateTime, default=datetime.now(timezone.utc))
    price = mapped_column(Float, nullable=False)
    volume = mapped_column(Float, nullable=False)
    
    # Fill quality
    fill_type = mapped_column(String(16), nullable=False, default="full")  # full, partial, rejected
    slippage = mapped_column(Float, nullable=False, default=0.0)
    
    # PnL impact
    pnl_impact = mapped_column(Float, nullable=False, default=0.0)
    commission = mapped_column(Float, nullable=False, default=0.0)
    swap = mapped_column(Float, nullable=False, default=0.0)
    
    # Market conditions at execution
    spread_at_execution = mapped_column(Float, nullable=False, default=0.0)
    volatility_at_execution = mapped_column(Float, nullable=False, default=0.0)
    
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# Market metrics table
class MarketMetrics(Base):
    __tablename__ = "market_metrics"
    __table_args__ = (
        UniqueConstraint("id", name="uq_market_metrics_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    symbol = mapped_column(String(32), nullable=False)
    bot_instance_id = mapped_column(String(128), nullable=False)
    
    # Time bucket
    bucket_start = mapped_column(DateTime, nullable=False)
    bucket_end = mapped_column(DateTime, nullable=False)
    
    # Metrics
    cotations_count = mapped_column(Integer, nullable=False, default=0)
    orders_count = mapped_column(Integer, nullable=False, default=0)
    fills_count = mapped_column(Integer, nullable=False, default=0)
    rejections_count = mapped_column(Integer, nullable=False, default=0)
    total_slippage = mapped_column(Float, nullable=False, default=0.0)
    total_commission = mapped_column(Float, nullable=False, default=0.0)
    total_swaps = mapped_column(Float, nullable=False, default=0.0)
    
    # Performance
    net_pnl = mapped_column(Float, nullable=False, default=0.0)
    gross_profit = mapped_column(Float, nullable=False, default=0.0)
    gross_loss = mapped_column(Float, nullable=False, default=0.0)
    win_rate = mapped_column(Float, nullable=False, default=0.0)
    
    # State
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# Chaos metrics table
class ChaosMetrics(Base):
    __tablename__ = "chaos_metrics"
    __table_args__ = (
        UniqueConstraint("id", name="uq_chaos_metrics_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    symbol = mapped_column(String(32), nullable=False)
    bot_instance_id = mapped_column(String(128), nullable=False)
    
    # Time bucket
    bucket_start = mapped_column(DateTime, nullable=False)
    bucket_end = mapped_column(DateTime, nullable=False)
    
    # Chaos metrics
    lyapunov_exp = mapped_column(Float, nullable=False, default=0.0)
    permutation_entropy = mapped_column(Float, nullable=False, default=0.0)
    hurst_exp = mapped_column(Float, nullable=False, default=0.5)
    chaos_score = mapped_column(Float, nullable=False, default=0.0)
    
    # Regime
    regime = mapped_column(String(32), nullable=False, default="ranging")
    
    # Time
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# Regime history table
class RegimeHistory(Base):
    __tablename__ = "regime_history"
    __table_args__ = (
        UniqueConstraint("id", name="uq_regime_history_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    bot_instance_id = mapped_column(String(128), nullable=False)
    symbol = mapped_column(String(32), nullable=False)
    
    regime = mapped_column(String(32), nullable=False)
    confidence = mapped_column(Float, nullable=False, default=0.5)
    
    # Time
    timestamp = mapped_column(DateTime, default=datetime.now(timezone.utc))
    duration_seconds = mapped_column(Integer, nullable=False, default=60)


# Risk events table
class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        UniqueConstraint("id", name="uq_risk_events_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    account_id = mapped_column(String(128), nullable=False)
    bot_instance_id = mapped_column(String(128), nullable=True)
    
    event_type = mapped_column(String(64), nullable=False)  # drawdown, margin, etc.
    severity = mapped_column(String(32), nullable=False, default="info")  # info, warning, critical
    
    description = mapped_column(Text, nullable=True)
    triggered_at = mapped_column(DateTime, default=datetime.now(timezone.utc))
    resolved_at = mapped_column(DateTime, nullable=True)
    
    # Action taken
    action_taken = mapped_column(Text, nullable=True)
    resolved = mapped_column(Boolean, nullable=False, default=False)
    
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# Bot logs table
class BotLogs(Base):
    __tablename__ = "bot_logs"
    __table_args__ = (
        UniqueConstraint("id", name="uq_bot_logs_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    bot_instance_id = mapped_column(String(128), nullable=False)
    
    level = mapped_column(String(16), nullable=False, default="INFO")  # DEBUG, INFO, WARNING, ERROR
    message = mapped_column(Text, nullable=False)
    component = mapped_column(String(64), nullable=True)
    
    # Context
    symbol = mapped_column(String(32), nullable=True)
    metadata = mapped_column(JSONB, nullable=True)
    
    logged_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# Performance snapshots table
class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint("id", name="uq_performance_snapshots_id"),
    )
    
    id = mapped_column(String(128), primary_key=True)
    bot_instance_id = mapped_column(String(128), nullable=False)
    symbol = mapped_column(String(32), nullable=False)
    
    # Metrics snapshot
    timestamp = mapped_column(DateTime, default=datetime.now(timezone.utc))
    
    # Key metrics
    balance = mapped_column(Float, nullable=False, default=10000.0)
    equity = mapped_column(Float, nullable=False, default=10000.0)
    total_pnl = mapped_column(Float, nullable=False, default=0.0)
    total_return_pct = mapped_column(Float, nullable=False, default=0.0)
    daily_pnl = mapped_column(Float, nullable=False, default=0.0)
    daily_return_pct = mapped_column(Float, nullable=False, default=0.0)
    
    # Trade metrics
    total_trades = mapped_column(Integer, nullable=False, default=0)
    winning_trades = mapped_column(Integer, nullable=False, default=0)
    losing_trades = mapped_column(Integer, nullable=False, default=0)
    win_rate = mapped_column(Float, nullable=False, default=0.0)
    
    # Risk metrics
    max_drawdown_pct = mapped_column(Float, nullable=False, default=0.0)
    current_drawdown_pct = mapped_column(Float, nullable=False, default=0.0)
    margin_utilization_pct = mapped_column(Float, nullable=False, default=0.0)
    
    # Chaos metrics
    chaos_score = mapped_column(Float, nullable=False, default=0.0)
    lyapunov_exp = mapped_column(Float, nullable=False, default=0.0)
    
    # State
    is_active = mapped_column(Boolean, nullable=False, default=True)
    
    created_at = mapped_column(DateTime, default=datetime.now(timezone.utc))


# ============================================================
# Migration/Initialization Functions
# ============================================================

async def init_db(async_url: str = DEFAULT_ASYNC_DATABASE_URL):
    """Initialize database - create all tables."""
    async_engine_local = create_async_engine(async_url)
    
    async with async_engine_local.begin() as conn:
        # Create all tables defined in Base
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    
    await async_engine_local.close()


async def drop_and_init_db(async_url: str = DEFAULT_ASYNC_DATABASE_URL):
    """Drop all tables and reinitialize (for testing)."""
    async_engine_local = create_async_engine(async_url)
    
    async with async_engine_local.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database reinitialized (all tables dropped and created)")


# ============================================================
# Database Helper Functions
# ============================================================

async def get_session(async_url: str = DEFAULT_ASYNC_DATABASE_URL) -> AsyncSession:
    """Get an async database session."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return session_factory()


# Common CRUD operations

async def create_record(session, model, **kwargs) -> Any:
    """Create a new database record."""
    stmt = insert(model).values(**kwargs).returning(model)
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()


async def get_record(session, model, id_value: str) -> Optional[Any]:
    """Get a database record by ID."""
    stmt = select(model).where(model.id == id_value)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_records(session, model, **filters) -> List[Any]:
    """Get multiple database records matching filters."""
    stmt = select(model).filter_by(**filters)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_record(session, model, id_value: str, **kwargs) -> Optional[Any]:
    """Update a database record."""
    stmt = update(model).where(model.id == id_value).values(**kwargs).returning(model)
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()


async def delete_record(session, model, id_value: str) -> bool:
    """Delete a database record."""
    stmt = delete(model).where(model.id == id_value)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


# Export main model base
__all__ = [
    "Base",
    "async_engine",
    "sync_engine",
    "init_db",
    "drop_and_init_db",
    "get_session",
    "create_record",
    "get_record",
    "get_records",
    "update_record",
    "delete_record",
    "Account",
    "Broker",
    "Symbol",
    "SymbolConfig",
    "BotInstance",
    "Position",
    "Order",
    "Execution",
    "MarketMetrics",
    "ChaosMetrics",
    "RegimeHistory",
    "RiskEvent",
    "BotLogs",
    "PerformanceSnapshot",
]
