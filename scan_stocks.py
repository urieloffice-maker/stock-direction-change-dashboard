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

WATCHLIST = [
    # טכנולוגיה
    "NVDA", "AAPL", "MSFT", "AVGO", "AMD",
    # פיננסים
    "JPM", "BAC", "GS", "MS",
    # תקשורת
    "GOOGL", "META", "NFLX",
    # צריכה מחזורית
    "AMZN", "TSLA", "HD",
    # תעשייה
    "CAT", "GE", "HON",
    # אנרגיה
    "XOM", "CVX", "COP",
    # בריאות
    "LLY", "UNH", "JNJ",
    # תשתיות
    "CEG", "VST", "NEE",
    # צריכה בסיסית
    "PG", "KO", "COST",
    # חומרים
    "LIN", "FCX", "NEM",
    # נדל״ן
    "PLD", "AMT", "SPG"
]

STOCK_SECTORS = {
    "NVDA": "טכנולוגיה", "AAPL": "טכנולוגיה", "MSFT": "טכנולוגיה", "AVGO": "טכנולוגיה", "AMD": "טכנולוגיה",
    "JPM": "פיננסים", "BAC": "פיננסים", "GS": "פיננסים", "MS": "פיננסים",
    "GOOGL": "תקשורת", "META": "תקשורת", "NFLX": "תקשורת",
    "AMZN": "צריכה מחזורית", "TSLA": "צריכה מחזורית", "HD": "צריכה מחזורית",
    "CAT": "תעשייה", "GE": "תעשייה", "HON": "תעשייה",
    "XOM": "אנרגיה", "CVX": "אנרגיה", "COP": "אנרגיה",
    "LLY": "בריאות", "UNH": "בריאות", "JNJ": "בריאות",
    "CEG": "תשתיות", "VST": "תשתיות", "NEE": "תשתיות",
    "PG": "צריכה בסיסית", "KO": "צריכה בסיסית", "COST": "צריכה בסיסית",
    "LIN": "חומרים", "FCX": "חומרים", "NEM": "חומרים",
    "PLD": "נדל״ן", "AMT": "נדל״ן", "SPG": "נדל״ן"
}

def fetch_skew():
    """שליפת מדד ה-SKEW לשורה התחתונה של תמחור סיכון זנב מוסדי"""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        tk = yf.Ticker("^SKEW", session=session)
        df = tk.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"Error fetching SKEW: {e}")
    return 130.0  # ערך ניטרלי כברירת מחדל

def check_earnings_soon(ticker_obj):
    """מסנן דוחות (Earnings Guard): בדיקה חסינה אם יש דוח ב-48 השעות הקרובות"""
    try:
        cal = ticker_obj.calendar
        if not cal:
            return False
        
        earn_dates = []
        if isinstance(cal, dict):
            earn_dates = cal.get('Earnings Date', [])
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                earn_dates = cal.loc['Earnings Date'].tolist()
            elif 'Earnings' in cal:
                earn_dates = cal['Earnings'].tolist()

        now = datetime.datetime.now()
        for ed in earn_dates:
            if isinstance(ed, (datetime.datetime, datetime.date)):
                ed_dt = datetime.datetime.combine(ed, datetime.time.min) if isinstance(ed, datetime.date) and not isinstance(ed, datetime.datetime) else ed
                diff_hours = (ed_dt - now).total_seconds() / 3600
                if 0 <= diff_hours <= 48:
                    return True
    except Exception as e:
        print(f"Earnings check error for {ticker_obj.ticker}: {e}")
    return False

def calculate_anchored_vwap(df, anchor_index):
    """חישוב Anchored VWAP מהשפל המקומי"""
    sub_df = df.iloc[anchor_index:].copy()
    tp = (sub_df['High'] + sub_df['Low'] + sub_df['Close']) / 3
    vwap = (tp * sub_df['Volume']).cumsum() / sub_df['Volume'].cumsum()
    return float(vwap.iloc[-1])

def send_telegram_opportunities(top_5, best_per_sector):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    message = "🔥 *Top 5 המניות החזקות בשוק (R/R >= 1:3)*\n\n"
    for item in top_5:
        earn_tag = " ⚠️ *EARNINGS SOON*" if item['earnings_soon'] else ""
        vwap_tag = " 🎯 *AVWAP Confluence*" if item['avwap_confluence'] else ""
        message += (
            f"📌 *{item['ticker']}* ({item['sector']}){earn_tag}{vwap_tag}\n"
            f"💵 נוכחי: `${item['current_price']}` | 🟢 **Limit:** `${item['entry_limit']}`\n"
            f"🔴 **Stop:** `${item['stop_loss']}` | 🎯 **Target:** `${item['target_price']}` (1:{item['rr_ratio']})\n"
            f"-----------------------------------\n"
        )

    message += "\n🌐 *המניה המובילה מכל סקטור (Best Per Sector)*\n\n"
    for item in best_per_sector:
        earn_tag = " ⚠️ *EARNINGS SOON*" if item['earnings_soon'] else ""
        message += (
            f"🏢 *{item['sector']}: {item['ticker']}*{earn_tag}\n"
            f"🟢 **Limit:** `${item['entry_limit']}` | 🔴 **Stop:** `${item['stop_loss']}` | 🎯 **Target:** `${item['target_price']}` (1:{item['rr_ratio']})\n"
            f"-----------------------------------\n"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
        print("Telegram dual opportunities alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def scan_opportunity(ticker, current_skew):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        tk = yf.Ticker(ticker, session=session)
        df = tk.history(period="1y")
        if df.empty or len(df) < 100:
            return None
        df.index = df.index.tz_localize(None)
    except Exception as e:
        print(f"Error fetching stock {ticker}: {e}")
        return None

    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    current_price = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma150 = float(close.rolling(150).mean().iloc[-1])

    # חישוב RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if loss.iloc[-1] != 0 else 50.0

    # חישוב ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    # 1. חישוב מחיר כניסה ב-Limit
    recent_low_10 = float(low.iloc[-10:].min())
    entry_limit = round(min(current_price * 0.99, max(recent_low_10, current_price - (0.8 * atr))), 2)

    # Stop Loss
    stop_loss = round(entry_limit - (1.2 * atr), 2)
    risk = entry_limit - stop_loss

    if risk <= 0:
        return None

    # יעד מחיר דינמי לפי שיא 60 יום
    recent_high_60 = float(high.iloc[-60:].max())
    target_price = round(max(recent_high_60, entry_limit + (3.0 * risk)), 2)
    reward = target_price - entry_limit

    # שידרוג 1: חישוב דינמי של R/R וסינון נוקשה (רק 1:3 ומעלה)
    rr_ratio = round(reward / risk, 2)
    if rr_ratio < 3.0:
        return None

    # שידרוג 3: מסנן דוחות (Earnings Guard)
    earnings_soon = bool(check_earnings_soon(tk))

    # שידרוג 5: Anchored VWAP מהשפל המקומי (למשל מנמוך 60 יום)
    local_low_idx = df.iloc[-60:]['Low'].idxmin()
    anchor_pos = df.index.get_loc(local_low_idx)
    avwap = calculate_anchored_vwap(df, anchor_pos)
    
    # בדיקת התלכדות (Confluence) בין מחיר ה-Limit ל-Anchored VWAP (טווח של 1.5%) - המרה ל-bool פייתוני רגיל
    avwap_confluence = bool(abs(entry_limit - avwap) / avwap <= 0.015)

    # חישוב הניקוד המשוקלל
    score = 0
    if current_price > sma150: score += 20
    if current_price > sma50: score += 15
    if 40 <= rsi <= 60: score += 20  # Pullback ב-Discount
    if float(volume.iloc[-1]) > float(volume.iloc[-20:].mean()): score += 15

    # שידרוג 4: התאמת ציון לפי SKEW (כשמדד ה-SKEW > 135 יש הסטה מוסדית להגנות)
    if current_skew > 135 and rsi < 50:
        score += 20  # ניצול Pullback איכותי בזמן הסטה מוסדית

    # תוספת ניקוד על התלכדות עם Anchored VWAP
    if avwap_confluence:
        score += 25

    # הורדת ניקוד חריפה אם יש דוח קרוב
    if earnings_soon:
        score -= 40

    return {
        "ticker": ticker,
        "sector": STOCK_SECTORS.get(ticker, "כללי"),
        "current_price": round(current_price, 2),
        "entry_limit": entry_limit,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "rr_ratio": rr_ratio,
        "rsi": round(rsi, 1),
        "avwap": round(avwap, 2),
        "avwap_confluence": avwap_confluence,
        "earnings_soon": earnings_soon,
        "score": score,
        "setup_type": "Pullback Limit" if rsi < 55 else "Trend Continuation"
    }

def filter_top5_with_sector_cap(opportunities, max_per_sector=2, max_total=5):
    """שידרוג 2: הגבלת חשיפה סקטוריאלית - מקסימום 2 מניות מכל סקטור ב-Top 5"""
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

def get_best_per_sector(opportunities):
    sector_best = {}
    for opp in opportunities:
        sec = opp["sector"]
        if sec not in sector_best or opp["score"] > sector_best[sec]["score"]:
            sector_best[sec] = opp
    return list(sector_best.values())

def main():
    print("Scanning stock opportunities with 5 Advanced Upgrades...")
    current_skew = fetch_skew()
    print(f"Current SKEW Index: {current_skew}")

    opportunities = []
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker, current_skew)
        if res:
            opportunities.append(res)
            
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    
    # 1. Top 5 עם מגבלת מקסימום 2 מניות לסקטור (Sector Cap)
    top_5_overall = filter_top5_with_sector_cap(opportunities, max_per_sector=2, max_total=5)
    
    # 2. המניה המובילה מכל סקטור
    best_per_sector = get_best_per_sector(opportunities)

    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data["stock_opportunities"] = top_5_overall
    data["best_per_sector_opportunities"] = best_per_sector
    data["skew_index"] = current_skew

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    send_telegram_opportunities(top_5_overall, best_per_sector)

    print("Scan complete with all 5 upgrades!")

if __name__ == "__main__":
    main()
