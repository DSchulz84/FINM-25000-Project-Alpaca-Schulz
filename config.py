#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
from dotenv import load_dotenv

# Process local system environment configurations
load_dotenv()

# =====================================================================
# SECURE BROKER DEPLOYMENT KEYS (NEVER HARD-CODED)
# =====================================================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

# =====================================================================
# INVESTMENT UNIVERSE & STORAGE SETTINGS
# =====================================================================
ENV_UNIVERSE_RAW = os.getenv("ASSET_UNIVERSE", "SPY,QQQ,IWM")
# String-to-Matrix Deserialization Engine
TICKERS = [ticker.strip() for ticker in ENV_UNIVERSE_RAW.split(",") if ticker.strip()]

STORAGE_DIRECTORY = os.getenv("STORAGE_DIRECTORY", "./data_storage")

# =====================================================================
# STRATEGY HYPER-PARAMETERS (ENVIRONMENT-LEVEL DEFAULTS)
# =====================================================================
DEFAULT_MA_WINDOW = int(os.getenv("DEFAULT_MA_WINDOW", "200"))
DEFAULT_RSI_LIMIT = int(os.getenv("DEFAULT_RSI_LIMIT", "60"))

# =====================================================================
# OPERATIONAL RISK CONTROL LIMITS (ENVIRONMENT-LEVEL DEFAULTS)
# =====================================================================
DEFAULT_RISK_PER_TRADE_PCT = float(os.getenv("DEFAULT_RISK_PER_TRADE_PCT", "1.0"))
DEFAULT_MAX_ASSET_EXPOSURE_PCT = float(os.getenv("DEFAULT_MAX_ASSET_EXPOSURE_PCT", "25.0"))

def verify_infrastructure():
    """Hard-stop check to block runtime execution if critical parameters are missing."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return False
    return True

