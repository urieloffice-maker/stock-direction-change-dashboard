import json
import os
import datetime
import requests
import pandas as pd
import yfinance as yf

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# רשימת מניות מובילות מכלל הסקטורים המובילים
WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AVGO", "AMD", "ARM", "AMAT", "LRCX", "TSM",
    "JPM", "BAC", "GS", "GOOGL", "META", "AMZN", "TSLA", "CAT", "GE",
    "XOM", "CVX", "LLY", "UNH", "CEG", "VST", "PLTR", "PANW", "ORCL"
]

def fetch_history(ticker):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        tk = yf.Ticker(ticker, session=session)
        df = tk.history(period="1y")
        if df.empty or len(df) < 100:
            return pd.DataFrame()
        df.index = df.index.tz_localize(None)
        return df
    except Exception as e:
        print(f"Error fetching stock {ticker}: {e}")
        return pd.DataFrame()

def scan_opportunity(ticker):
    df = fetch_history(ticker)
    if df.empty:
        return None

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    current_price = close.iloc[-1]
    
    sma50 = close.rolling(50).mean().iloc[-1]
    sma150 = close.rolling(150).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]

    # חישוב RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 50

    # חישוב ATR (14)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # הגדרת מחיר כניסה מומלץ (Limit Price) בנסיגה קלה/תמיכה
    recent_low = low.iloc[-10:].min()
    entry_limit = round(min(current_price * 0.99, max(recent_low, current_price - (0.8 * atr))), 2)

    # קטיעת הפסד (Stop Loss) מבוסס ATR
    stop_loss = round(entry_limit - (1.5 * atr), 2)
    risk_per_share = entry_limit - stop_loss

    if risk_per_share <= 0:
        return None

    # יעד רווח (Take Profit) - יחס 1:2.2 לפחות
    target_price = round(entry_limit + (2.2 * risk_per_share), 2)
    rr_ratio = round((target_price - entry_limit) / risk_per_share, 2)

    # ניקוד הסטאפ
    score = 0
    if current_price > sma150: score += 30
    if current_price > sma50: score += 20
    if 40 <= rsi <= 65: score += 25
    if volume.iloc[-1] > volume.iloc[-20:].mean(): score += 25

    return {
        "ticker": ticker,
        "current_price": round(current_price, 2),
        "entry_limit": entry_limit,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "rr_ratio": rr_ratio,
        "rsi": round(rsi, 1),
        "score": score,
        "setup_type": "Pullback Limit" if rsi < 55 else "Trend Continuation"
    }

def main():
    print("Scanning stock opportunities...")
    opportunities = []
    
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker)
        if res:
            opportunities.append(res)
            
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    top_opportunities = opportunities[:5]  # בחירת 5 המניות החזקות ביותר

    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["stock_opportunities"] = top_opportunities

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Scan complete! Displaying top {len(top_opportunities)} stocks.")

if __name__ == "__main__":
    main()
