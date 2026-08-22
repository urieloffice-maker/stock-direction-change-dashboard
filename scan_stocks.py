import json
import os
import datetime
import requests
import pandas as pd
import yfinance as yf

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# רשימת מניות ליבה מגוונת לפי סקטורים לבחינה
WATCHLIST = [
    # XLK
    "NVDA", "AAPL", "MSFT", "AVGO", "AMD", "ARM", "AMAT", "LRCX",
    # XLF / XLC / XLY / XLI
    "JPM", "BAC", "GS", "GOOGL", "META", "AMZN", "TSLA", "CAT", "GE",
    # XLE / XLV / XLU
    "XOM", "CVX", "LLY", "UNH", "CEG", "VST"
]

def fetch_history(ticker):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        tk = yf.Ticker(ticker, session=session)
        df = tk.history(period="1y")
        if df.empty or len(df) < 150:
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
    
    # ממוצעים נעים
    sma50 = close.rolling(50).mean().iloc[-1]
    sma150 = close.rolling(150).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]

    # תנאי סף: מגמה עולה ראשית
    if not (current_price > sma150 and current_price > sma200):
        return None

    # חישוב RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    # חישוב ATR (14)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # זיהוי מחיר כניסה בלימיט (Limit Price) בתיקון בריא אל מול תמיכה/ממוצע נע
    recent_low = low.iloc[-10:].min()
    entry_limit = round(max(recent_low, sma50), 2)
    
    # במידה והמחיר כבר צמוד לתמיכה
    if entry_limit >= current_price:
        entry_limit = round(current_price * 0.985, 2)

    # סטופ לוס (Stop Loss) מבוסס ATR מתחת למחיר הכניסה
    stop_loss = round(entry_limit - (1.5 * atr), 2)
    risk_per_share = entry_limit - stop_loss

    if risk_per_share <= 0:
        return None

    # יעד מחיר (Take Profit) - יחס סיכון/סיכוי של לפחות 1:2.5
    target_price = round(entry_limit + (2.5 * risk_per_share), 2)
    rr_ratio = round((target_price - entry_limit) / risk_per_share, 2)

    # ציון איכות הסטאפ
    score = 0
    if 40 <= rsi <= 55: score += 30  # RSI באזור תיקון בריא
    if current_price > sma50: score += 25
    if volume.iloc[-1] > volume.iloc[-20:].mean() * 1.2: score += 25  # ווליום תומך
    if rr_ratio >= 2.5: score += 20

    if score >= 50:
        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "entry_limit": entry_limit,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "rr_ratio": rr_ratio,
            "rsi": round(rsi, 1),
            "score": score,
            "setup_type": "Pullback & Support Limit" if rsi < 55 else "Breakout Continuation"
        }
    return None

def main():
    print("Scanning stocks for high-probability setups...")
    opportunities = []
    
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker)
        if res:
            opportunities.append(res)
            
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    opportunities = opportunities[:5]  # 5 ההזדמנויות המובילות

    # עדכון קובץ data.json
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["stock_opportunities"] = opportunities

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Scan complete! Found {len(opportunities)} opportunities.")

if __name__ == "__main__":
    main()
