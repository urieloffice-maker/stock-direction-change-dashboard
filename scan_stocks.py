import json
import os
import datetime
import urllib.request
import urllib.parse
import requests
import pandas as pd
import yfinance as yf

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# רשימת המניות הראשיות לבדיקה
WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "AVGO", "AMD", "ARM", "AMAT", "LRCX", "TSM",
    "JPM", "BAC", "GS", "GOOGL", "META", "AMZN", "TSLA", "CAT", "GE",
    "XOM", "CVX", "LLY", "UNH", "CEG", "VST", "PLTR", "PANW", "ORCL"
]

# מיפוי מניות לסקטורים
STOCK_SECTORS = {
    "NVDA": "טכנולוגיה", "AAPL": "טכנולוגיה", "MSFT": "טכנולוגיה", "AVGO": "טכנולוגיה", 
    "AMD": "טכנולוגיה", "ARM": "טכנולוגיה", "AMAT": "טכנולוגיה", "LRCX": "טכנולוגיה", "TSM": "טכנולוגיה",
    "JPM": "פיננסים", "BAC": "פיננסים", "GS": "פיננסים", 
    "GOOGL": "תקשורת", "META": "תקשורת", 
    "AMZN": "צריכה מחזורית", "TSLA": "צריכה מחזורית", 
    "CAT": "תעשייה", "GE": "תעשייה",
    "XOM": "אנרגיה", "CVX": "אנרגיה", 
    "LLY": "בריאות", "UNH": "בריאות", 
    "CEG": "תשתיות", "VST": "תשתיות", 
    "PLTR": "טכנולוגיה", "PANW": "טכנולוגיה", "ORCL": "טכנולוגיה"
}

def send_telegram_opportunities(opportunities):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id or not opportunities:
        return

    message = "🎯 *הזדמנויות מסחר מסוננות (Sector Cap & Dynamic R/R)*\n\n"
    for item in opportunities:
        message += (
            f"📌 *{item['ticker']}* ({item['sector']})\n"
            f"💵 מחיר נוכחי: `${item['current_price']}`\n"
            f"🟢 **כניסה ב-Limit:** `${item['entry_limit']}`\n"
            f"🔴 **Stop Loss:** `${item['stop_loss']}`\n"
            f"🎯 **Target:** `${item['target_price']}` (יחס 1:{item['rr_ratio']})\n"
            f"📊 RSI: {item['rsi']}\n"
            f"-----------------------------------\n"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
        print("Telegram opportunities alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

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

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 50

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    # מחיר כניסה מומלץ (Limit Price) בנסיגה
    recent_low = low.iloc[-10:].min()
    entry_limit = round(min(current_price * 0.99, max(recent_low, current_price - (0.8 * atr))), 2)

    # Stop Loss מבוסס ATR
    stop_loss = round(entry_limit - (1.5 * atr), 2)
    risk = entry_limit - stop_loss

    if risk <= 0:
        return None

    # חישוב דינמי של יעד הרווח (Target Price) לפי השיא ב-50 ימים האחרונים
    recent_high = high.iloc[-50:].max()
    target_price = round(max(recent_high, entry_limit + (2.0 * risk)), 2)
    
    reward = target_price - entry_limit
    
    # חישוב דינמי של יחס הסיכון/סיכוי (R/R)
    rr_ratio = round(reward / risk, 2)

    if rr_ratio < 1.8:
        return None

    score = 0
    if current_price > sma150: score += 30
    if current_price > sma50: score += 20
    if 40 <= rsi <= 65: score += 25
    if volume.iloc[-1] > volume.iloc[-20:].mean(): score += 25
    score += min(int(rr_ratio * 10), 30)

    return {
        "ticker": ticker,
        "sector": STOCK_SECTORS.get(ticker, "כללי"),
        "current_price": round(current_price, 2),
        "entry_limit": entry_limit,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "rr_ratio": rr_ratio,
        "rsi": round(rsi, 1),
        "score": score,
        "setup_type": "Pullback Limit" if rsi < 55 else "Trend Continuation"
    }

def filter_by_sector_cap(opportunities, max_per_sector=1, max_total=5):
    sector_counts = {}
    filtered = []
    
    for opp in opportunities:
        sec = opp["sector"]
        count = sector_counts.get(sec, 0)
        if count < max_per_sector:
            filtered.append(opp)
            sector_counts[sec] = count + 1
            if len(filtered) == max_total:
                break
    return filtered

def main():
    print("Scanning stock opportunities with Sector Cap & Dynamic R/R...")
    opportunities = []
    
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker)
        if res:
            opportunities.append(res)
            
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    
    # מגבלת חשיפה סקטוריאלית (מניה אחת מכל סקטור)
    top_opportunities = filter_by_sector_cap(opportunities, max_per_sector=1, max_total=5)

    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["stock_opportunities"] = top_opportunities

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    send_telegram_opportunities(top_opportunities)

    print(f"Scan complete! Selected {len(top_opportunities)} diversified opportunities.")

if __name__ == "__main__":
    main()
