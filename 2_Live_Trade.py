#!/usr/bin/env python
# coding: utf-8

# In[ ]:

import sys
import os

# Force Python to find config.py at the root level if a subpage runs independently
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import os
import datetime
import time
import logging
import pandas as pd
import streamlit as st
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError

st.set_page_config(page_title="Live Execution Desk", layout="wide")

# =====================================================================
# LIFECYCLE REFRESH SAFEGUARD: LOCAL BOUNDARY FALLBACK BINDING ROUTINE
# =====================================================================
if "universe" not in st.session_state:
    raw_env_univ = os.getenv("ASSET_UNIVERSE", "SPY,QQQ,IWM")
    st.session_state.universe = [t.strip() for t in raw_env_univ.split(",") if t.strip()]
if "storage_dir" not in st.session_state: 
    st.session_state.storage_dir = os.getenv("STORAGE_DIRECTORY", "./data_storage")
if "risk_pct" not in st.session_state: 
    st.session_state.risk_pct = float(os.getenv("DEFAULT_RISK_PER_TRADE_PCT", "1.0"))
if "exposure_pct" not in st.session_state: 
    st.session_state.exposure_pct = float(os.getenv("DEFAULT_MAX_ASSET_EXPOSURE_PCT", "25.0"))
if "rsi_limit" not in st.session_state: 
    st.session_state.rsi_limit = int(os.getenv("DEFAULT_RSI_LIMIT", "60"))
if "ma_window" not in st.session_state: 
    st.session_state.ma_window = int(os.getenv("DEFAULT_MA_WINDOW", "200"))
if "metrics" not in st.session_state:
    st.session_state.metrics = {"api_calls_count": 0, "api_failures_count": 0, "signals_generated": 0, "signals_rejected_risk": 0, "last_run_duration": 0.0}

logger = logging.getLogger("SystematicEngine")

# Instantiating Multi-Asset Endpoints from Runtime Configuration Dictionary
data_client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
trading_client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)

RISK_PER_TRADE_PCT = st.session_state.risk_pct / 100
MAX_ASSET_EXPOSURE_PCT = st.session_state.exposure_pct / 100
ASSET_UNIVERSE = st.session_state.universe
STORAGE_DIR = st.session_state.storage_dir
UI_MA_WINDOW = st.session_state.ma_window
UI_RSI_LIMIT = st.session_state.rsi_limit

def fetch_and_store_universe(universe):
    st.session_state.metrics["api_calls_count"] += 1
    end_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)
    start_date = end_date - datetime.timedelta(days=365)
    request_params = StockBarsRequest(symbol_or_symbols=universe, timeframe=TimeFrame.Day, start=start_date, end=end_date)

    try:
        raw_bars = data_client.get_stock_bars(request_params).df
        return {t: raw_bars.xs(t, level=0).copy() for t in universe if t in raw_bars.index.get_level_values(0)}
    except Exception as e:
        st.session_state.metrics["api_failures_count"] += 1
        st.error(f"Failed to access network bars: {str(e)}")
        return {}

def engineering_features(df):
    df = df.copy()
    df['SMA_Trend'] = df['close'].rolling(window=UI_MA_WINDOW).mean()
    df['SMA_Trend_20_days_ago'] = df['SMA_Trend'].shift(20)

    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD_Line'] = ema_12 - ema_26
    df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD_Line'] - df['Signal_Line']

    df['MACD_Hist_Prev1'] = df['MACD_Hist'].shift(1)
    df['MACD_Hist_Prev2'] = df['MACD_Hist'].shift(2)

    cond_hist_below_zero = (df['MACD_Hist'] < 0) & (df['MACD_Hist_Prev1'] < 0)
    cond_hist_turnaround = (df['MACD_Hist'] > df['MACD_Hist_Prev1']) & (df['MACD_Hist_Prev1'] < df['MACD_Hist_Prev2'])
    cond_momentum = cond_hist_below_zero & cond_hist_turnaround

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI_14'] = 100 - (100 / (1 + rs))

    high_low = df['high'] - df['low']
    high_close_prev = (df['high'] - df['close'].shift(1)).abs()
    low_close_prev = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    df['ATR_14'] = tr.rolling(window=14).mean()

    cond_stability = (df['close'] > df['SMA_Trend']) & (df['SMA_Trend'] > df['SMA_Trend_20_days_ago'])
    cond_rsi = df['RSI_14'] < UI_RSI_LIMIT

    df['entry_signal'] = (cond_stability & cond_momentum & cond_rsi).astype(int)
    df.dropna(subset=['SMA_Trend_20_days_ago', 'ATR_14', 'RSI_14', 'MACD_Hist_Prev2'], inplace=True)
    return df

def execute_paper_trade_signal(ticker, processed_df, account, positions):
    try:
        last_row = processed_df.iloc[[-1]]
        signal = last_row['entry_signal'].values[0]
        has_position = any(p.symbol == ticker for p in positions)

        if signal == 1:
            st.session_state.metrics["signals_generated"] += 1
            if not has_position:
                current_price, current_atr = last_row['close'].values[0], last_row['ATR_14'].values[0]
                calculated_qty = int((float(account.portfolio_value) * RISK_PER_TRADE_PCT) / (3.0 * current_atr))
                calculated_qty = max(1, calculated_qty)

                if (calculated_qty * current_price) > (float(account.portfolio_value) * MAX_ASSET_EXPOSURE_PCT):
                    calculated_qty = int((float(account.portfolio_value) * MAX_ASSET_EXPOSURE_PCT) / current_price)
                if (calculated_qty * current_price) > float(account.cash):
                    calculated_qty = int(float(account.cash) / current_price) - 1

                if calculated_qty <= 0:
                    st.session_state.metrics["signals_rejected_risk"] += 1
                    return

                try:
                    st.session_state.metrics["api_calls_count"] += 1
                    trading_client.submit_order(order_data=MarketOrderRequest(
                        symbol=ticker, qty=calculated_qty, side=OrderSide.BUY, time_in_force=TimeInForce.GTC
                    ))
                    st.toast(f"🚀 Live Order Transmitted: {ticker} x {calculated_qty}", icon="💸")
                except APIError as api_err:
                    st.session_state.metrics["api_failures_count"] += 1
                    logger.error(f"[ALPACA REJECTION] Error: {ticker}. Message: {str(api_err)}")
                    st.error(f"🛑 Alpaca Rejected Trade for {ticker}: {api_err.message}")
    except Exception as e:
        st.session_state.metrics["api_failures_count"] += 1
        logger.critical(f"[SYSTEM FAILURE] {str(e)}")

st.title("🏦 Broker Account Real-Time Positions")

try:
    st.session_state.metrics["api_calls_count"] += 1
    account = trading_client.get_account()

    st.session_state.metrics["api_calls_count"] += 1
    clock = trading_client.get_clock()

    if account.trading_blocked or account.status != 'ACTIVE':
        st.error("🚨 CRITICAL ACCOUNT ERROR: Your Alpaca account is currently blocked or inactive. Trading is disabled.")
        st.stop()

    st.session_state.metrics["api_calls_count"] += 1
    positions = trading_client.get_all_positions()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net Liquidity Value", f"${float(account.portfolio_value):,.2f}")
    col2.metric("Total Buying Power", f"${float(account.buying_power):,.2f}")
    col3.metric("Liquid Cash Balance", f"${float(account.cash):,.2f}")
    col4.metric("Active Risk Vectors", f"{len(positions)}")

    st.markdown("#### Current Portfolio Allocations")
    if positions:
        pos_data = [{
            "Ticker": p.symbol, "Market Position": p.qty, 
            "Avg Entry Price": f"${float(p.avg_entry_price):,.2f}", 
            "Current Price": f"${float(p.current_price):,.2f}", 
            "Market Value": f"${float(p.market_value):,.2f}", 
            "Floating Unr. P&L": f"${float(p.unrealized_pl):,.2f}"
        } for p in positions]
        st.dataframe(pd.DataFrame(pos_data), use_container_width=True)
    else:
        st.info("No active asset positions open currently.")

    st.markdown("---")
    st.subheader("⚡ Live Production Scanner Execution")

    if not clock.is_open:
        st.warning(f"⚠️ MARKET IS CLOSED. Next opening session: {clock.next_open.strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        st.success("🟢 Market is currently OPEN. Signals will fill immediately with live liquidity.")

    if st.button("📡 Scan Today's Signals & Route Orders"):
        start_timer = time.time()
        with st.spinner("Processing live universe feature engineering frames..."):
            universe_frames = fetch_and_store_universe(ASSET_UNIVERSE)
            for ticker, df_raw in universe_frames.items():
                df_engineered = engineering_features(df_raw)
                execute_paper_trade_signal(ticker, df_engineered, account, positions)
        st.success("Scanner complete. Live paper routing operations sync completed.")
        st.session_state.metrics["last_run_duration"] = time.time() - start_timer

except Exception as e:
    st.session_state.metrics["api_failures_count"] += 1
    st.error(f"Failed to access active live execution account endpoints: {str(e)}")

