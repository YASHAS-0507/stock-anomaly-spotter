"""
ticker_registry.py
------------------
Angel One NSE token registry and sector map for Nifty 50 stocks.
Token numbers are the official Angel One instrument tokens for NSE Cash Market.
"""

from typing import Optional

# NSE instrument tokens as used by Angel One SmartAPI
# Format: "TICKER.NS" → Angel One token string
NIFTY_50_TOKENS: dict[str, str] = {
    # Ticker           Token
    "RELIANCE.NS":    "2885",
    "TCS.NS":         "11536",
    "HDFCBANK.NS":    "1333",
    "INFY.NS":        "1594",
    "ICICIBANK.NS":   "4963",
    "SBIN.NS":        "3045",
    "WIPRO.NS":       "3787",
    "AXISBANK.NS":    "5900",
    "KOTAKBANK.NS":   "1922",
    "LT.NS":          "11483",
    "TATAMOTORS.NS":  "3456",
    "MARUTI.NS":      "10999",
    "SUNPHARMA.NS":   "3351",
    "BAJFINANCE.NS":  "317",
    "TITAN.NS":       "3506",
    "HINDUNILVR.NS":  "1394",
    "ASIANPAINT.NS":  "236",
    "BHARTIARTL.NS":  "10604",
    "ITC.NS":         "1660",
    "HCLTECH.NS":     "7229",
    "POWERGRID.NS":   "14977",
    "NTPC.NS":        "11630",
    "ONGC.NS":        "2475",
    "COALINDIA.NS":   "20374",
    "JSWSTEEL.NS":    "11723",
    "TATASTEEL.NS":   "3499",
    "TECHM.NS":       "13538",
    "DRREDDY.NS":     "881",
    "CIPLA.NS":       "694",
    "DIVISLAB.NS":    "10940",
    "ADANIPORTS.NS":  "15083",
    "HINDALCO.NS":    "1363",
    "ULTRACEMCO.NS":  "11532",
    "GRASIM.NS":      "1232",
    "BAJAJFINSV.NS":  "16675",
    "BAJAJ-AUTO.NS":  "16669",
    "HDFCLIFE.NS":    "467",
    "SBILIFE.NS":     "21808",
    "INDUSINDBK.NS":  "5258",
    "EICHERMOT.NS":   "910",
    "HEROMOTOCO.NS":  "1348",
    "BRITANNIA.NS":   "547",
    "BPCL.NS":        "526",
    "TATACONSUM.NS":  "3432",
    "APOLLOHOSP.NS":  "157",
    "NESTLEIND.NS":   "17963",
    "M&M.NS":         "2031",
    "SHREECEM.NS":    "3103",
    "UPL.NS":         "11287",
    "WIPRO.NS":       "3787",
}

# Sector map — used to prevent two positions in the same sector simultaneously
SECTOR_MAP: dict[str, str] = {
    "RELIANCE.NS":    "Energy",
    "TCS.NS":         "Technology",
    "HDFCBANK.NS":    "Banking",
    "INFY.NS":        "Technology",
    "ICICIBANK.NS":   "Banking",
    "SBIN.NS":        "Banking",
    "WIPRO.NS":       "Technology",
    "AXISBANK.NS":    "Banking",
    "KOTAKBANK.NS":   "Banking",
    "LT.NS":          "Infrastructure",
    "TATAMOTORS.NS":  "Automobile",
    "MARUTI.NS":      "Automobile",
    "SUNPHARMA.NS":   "Pharma",
    "BAJFINANCE.NS":  "NBFC",
    "TITAN.NS":       "Consumer Goods",
    "HINDUNILVR.NS":  "FMCG",
    "ASIANPAINT.NS":  "Consumer Goods",
    "BHARTIARTL.NS":  "Telecom",
    "ITC.NS":         "FMCG",
    "HCLTECH.NS":     "Technology",
    "POWERGRID.NS":   "Power",
    "NTPC.NS":        "Power",
    "ONGC.NS":        "Energy",
    "COALINDIA.NS":   "Energy",
    "JSWSTEEL.NS":    "Metals",
    "TATASTEEL.NS":   "Metals",
    "TECHM.NS":       "Technology",
    "DRREDDY.NS":     "Pharma",
    "CIPLA.NS":       "Pharma",
    "DIVISLAB.NS":    "Pharma",
    "ADANIPORTS.NS":  "Infrastructure",
    "HINDALCO.NS":    "Metals",
    "ULTRACEMCO.NS":  "Cement",
    "GRASIM.NS":      "Cement",
    "BAJAJFINSV.NS":  "NBFC",
    "BAJAJ-AUTO.NS":  "Automobile",
    "HDFCLIFE.NS":    "Insurance",
    "SBILIFE.NS":     "Insurance",
    "INDUSINDBK.NS":  "Banking",
    "EICHERMOT.NS":   "Automobile",
    "HEROMOTOCO.NS":  "Automobile",
    "BRITANNIA.NS":   "FMCG",
    "BPCL.NS":        "Energy",
    "TATACONSUM.NS":  "FMCG",
    "APOLLOHOSP.NS":  "Healthcare",
    "NESTLEIND.NS":   "FMCG",
    "M&M.NS":         "Automobile",
    "SHREECEM.NS":    "Cement",
    "UPL.NS":         "Chemicals",
}


def get_token(ticker: str) -> Optional[str]:
    """Return the Angel One NSE token for a ticker, or None if not registered."""
    return NIFTY_50_TOKENS.get(ticker)


def get_sector(ticker: str) -> Optional[str]:
    """Return the sector for a ticker, or None if not registered."""
    return SECTOR_MAP.get(ticker)


def get_ticker_by_token(token: str) -> Optional[str]:
    """Reverse lookup: Angel One token → ticker symbol."""
    for ticker, t in NIFTY_50_TOKENS.items():
        if t == token:
            return ticker
    return None
