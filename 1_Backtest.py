#!/usr/bin/env python
# coding: utf-8

# In[ ]:

import sys
import os

# Force Python to find config.py at the root level if a subpage runs independently
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="backtesting")

import os
import datetime
import time
import pandas as pd
import streamlit as st
from backtesting import Backtest, Strategy
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.historical import StockHistoricalDataClient

st.set_page_config(page_title="Historical Backtest Sandbox", layout="wide")

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

# Instantiating Data Connectors from Secure Environment Strings
data_client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

# Unpacking Active Hyper-Parameters from State Vectors
RISK_PER_TRADE_PCT = st.session_state.risk_pct / 100
MAX_ASSET_EXPOSURE_PCT = st.session_state.exposure_pct / 100
ASSET_UNIVERSE = st.session_state.universe
STORAGE_DIR = st.session_state.storage_dir
UI_MA_WINDOW = st.session_state.ma_window
UI_RSI_LIMIT = st.session_state.rsi_limit

def fetch_and_store_universe(universe, years=5):
    st.session_state.metrics["api_calls_count"] += 1
    end_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=20)
    start_date = end_date - datetime.timedelta(days=years * 365)
    request_params = StockBarsRequest(symbol_or_symbols=universe, timeframe=TimeFrame.Day, start=start_date, end=end_date)

    try:
        raw_bars = data_client.get_stock_bars(request_params).df
    except Exception as e:
        st.session_state.metrics["api_failures_count"] += 1
        st.error(f"Failed to access historical endpoints: {str(e)}")
        return {}

    universe_data = {}
    for ticker in universe:
        if ticker in raw_bars.index.get_level_values(0):
            df_bars = raw_bars.xs(ticker, level=0).copy()
            df_bars.index = pd.to_datetime(df_bars.index).tz_localize(None)
            df_bars.to_csv(os.path.join(STORAGE_DIR, f"{ticker}.csv"))
            universe_data[ticker] = df_bars
    return universe_data

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

class DualPathMomentumStrategy(Strategy):
    def init(self):
        self.entry_sig = self.I(lambda: self.data.entry_signal)
        self.atr = self.I(lambda: self.data.ATR_14)
        self.initial_atr, self.milestone_target, self.highest_close = None, None, None
        self.t = 0
        self.hyper_growth_mode = False

    def next(self):
        if not self.position:
            if self.entry_sig[-1] == 1:
                current_price, current_atr = self.data.Close[-1], self.atr[-1]
                target_qty = (self.equity * RISK_PER_TRADE_PCT) / (3.0 * current_atr)

                if (target_qty * current_price) > (self.equity * MAX_ASSET_EXPOSURE_PCT):
                    target_qty = (self.equity * MAX_ASSET_EXPOSURE_PCT) / current_price
                if (target_qty * current_price) > self.equity: 
                    target_qty = max(0, int(self.equity / current_price) - 1)

                final_qty = int(target_qty)
                if final_qty > 0:
                    self.buy(size=final_qty)
                    self.initial_atr, self.highest_close, self.t, self.hyper_growth_mode = current_atr, current_price, 0, False
                    self.milestone_target = current_price + (3.5 * current_atr)
            return

        self.t += 1
        current_close = self.data.Close[-1]
        if current_close > self.highest_close: self.highest_close = current_close
        if not self.hyper_growth_mode and current_close >= self.milestone_target: self.hyper_growth_mode = True

        if self.hyper_growth_mode:
            if current_close <= (self.highest_close - (2.0 * self.initial_atr)): self.position.close()
        else:
            stop_multiplier = 3.0 - (0.05 * self.t)
            if current_close <= (self.highest_close - (stop_multiplier * self.initial_atr)): self.position.close()
            elif self.t >= 60: self.position.close()

st.title("📊 Historical Strategy Performance Scanner")
st.write(f"Simulating performance across {len(ASSET_UNIVERSE)} assets loaded dynamically from parameter configuration files.")

if st.button("🚀 Execute Portfolio Engine Run"):
    start_timer = time.time()
    with st.spinner("Re-indexing local matrix databases and simulating performance..."):
        universe_frames = fetch_and_store_universe(ASSET_UNIVERSE, years=5)

        grid_metrics = []
        portfolio_equity_curves = []

        for ticker, df_raw in universe_frames.items():
            df_engineered = engineering_features(df_raw)

            df_test = df_engineered.copy().rename(columns={'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'})
            bt = Backtest(df_test, DualPathMomentumStrategy, cash=100000, commission=.000, finalize_trades=True)
            stats = bt.run()

            eq_curve = stats['_equity_curve']['Equity']
            portfolio_equity_curves.append(eq_curve)

            last_row = df_engineered.iloc[-1]
            signal_desc = "🟢 ENTRY HIT" if last_row['entry_signal'] == 1 else "⚪ WAITING"

            grid_metrics.append({
                "Ticker": ticker, 
                "Total Return": f"{stats.get('Return [%]', 0.0):.2f}%",
                "Max Drawdown": f"{stats.get('Max Drawdown [%]', 0.0):.2f}%",
                "Total Trades": int(stats.get('# Trades', 0)),
                "Current RSI": f"{last_row['RSI_14']:.1f}",
                "State Tracker": signal_desc
            })

    st.session_state.metrics["last_run_duration"] = time.time() - start_timer

    st.markdown("#### Backtest Simulation Performance Analytics")
    st.dataframe(pd.DataFrame(grid_metrics), use_container_width=True)

