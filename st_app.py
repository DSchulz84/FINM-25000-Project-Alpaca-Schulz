#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import logging
import streamlit as st
from dotenv import load_dotenv

# Set page layout configuration immediately at the top entry level
st.set_page_config(page_title="Enterprise Workspace Engine", layout="wide")

# Read environmental properties from the local environment
load_dotenv()

# Extract API Keys and Invariant Configurations
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ENV_UNIVERSE_RAW = os.getenv("ASSET_UNIVERSE", "SPY,QQQ,IWM")

# Hard Stop Interceptor: Block application if infrastructure strings are missing
if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    st.error("CRITICAL ERROR: Alpaca API Keys not found. Please verify your .env file setup.")
    st.stop()

# Deserialization Matrix Step
ST_UNIVERSE = [ticker.strip() for ticker in ENV_UNIVERSE_RAW.split(",") if ticker.strip()]
ST_STORAGE_DIR = os.getenv("STORAGE_DIRECTORY", "./data_storage")
os.makedirs(ST_STORAGE_DIR, exist_ok=True)

# Cache immutable structural arrays into application session state layers
if "universe" not in st.session_state: st.session_state.universe = ST_UNIVERSE
if "storage_dir" not in st.session_state: st.session_state.storage_dir = ST_STORAGE_DIR

# Establish Unified Real-time Telemetry Data Primitives
if "metrics" not in st.session_state:
    st.session_state.metrics = {
        "api_calls_count": 0,
        "api_failures_count": 0,
        "signals_generated": 0,
        "signals_rejected_risk": 0,
        "last_run_duration": 0.0,
        "total_assets_processed": 0
    }

# =====================================================================
# SIDEBAR CONFIGURATION DESK (DRIVEN BY ENV VARIABLE DEFAULT DEFAULTS)
# =====================================================================
st.sidebar.title("🎛️ Shared Core Configurations")
st.sidebar.markdown("Changes here apply to both Backtesting and Live Trade modes.")

if "risk_pct" not in st.session_state: 
    st.session_state.risk_pct = float(os.getenv("DEFAULT_RISK_PER_TRADE_PCT", "1.0"))
if "exposure_pct" not in st.session_state: 
    st.session_state.exposure_pct = float(os.getenv("DEFAULT_MAX_ASSET_EXPOSURE_PCT", "25.0"))
if "rsi_limit" not in st.session_state: 
    st.session_state.rsi_limit = int(os.getenv("DEFAULT_RSI_LIMIT", "60"))
if "ma_window" not in st.session_state: 
    st.session_state.ma_window = int(os.getenv("DEFAULT_MA_WINDOW", "200"))

# Dynamic Slider Binds
st.session_state.risk_pct = st.sidebar.slider("Risk Per Trade (%)", 0.1, 5.0, st.session_state.risk_pct, step=0.1)
st.session_state.exposure_pct = st.sidebar.slider("Max Asset Exposure (%)", 5.0, 50.0, st.session_state.exposure_pct, step=1.0)
st.session_state.rsi_limit = st.sidebar.slider("RSI Entry Ceiling", 40, 70, st.session_state.rsi_limit, step=1)
st.session_state.ma_window = st.sidebar.slider("Trend Filter Window (SMA Days)", 20, 200, st.session_state.ma_window, step=5)

# Initialize Platform-Wide Log File Output Pipeline
logger = logging.getLogger("SystematicEngine")
logger.setLevel(logging.INFO)
if logger.hasHandlers(): logger.handlers.clear()
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [Module: %(module)s] %(message)s")
file_handler = logging.FileHandler("system_pipeline.log")
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Main UI Display Rendering Routing
st.title("🛡️ Core System Command Center")
st.markdown("Welcome to the quantitative framework command deck. Use the side index menu to navigate between pages.")
st.markdown("---")

st.subheader("🖥️ Central Architectural Health & Pipeline Metrics")
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
m_col1.metric("Total API Requests", st.session_state.metrics["api_calls_count"])
m_col2.metric("API Request Errors", st.session_state.metrics["api_failures_count"])
m_col3.metric("Flashed Trade Signals", st.session_state.metrics["signals_generated"])
m_col4.metric("Risk Sizing Rejections", st.session_state.metrics["signals_rejected_risk"])
m_col5.metric("Last Operational Latency", f"{st.session_state.metrics['last_run_duration']:.2f}s")
st.markdown("---")
st.info("💡 **Multi-Page Configuration Notice:** Environmental settings successfully bound from variable definitions.")

