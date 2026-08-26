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
    "NVDA", "AAPL", "MSFT", "AVGO", "AMD",
    "JPM", "BAC", "GS", "MS",
    "GOOGL", "META", "NFLX",
    "AMZN", "TSLA", "HD",
    "CAT", "GE", "HON",
    "XOM", "CVX", "COP",
    "LLY", "UNH", "JNJ",
    "CEG", "VST", "NEE",
    "PG", "KO", "COST",
    "LIN", "FCX", "NEM",
    "PLD", "AMT", "SPG"
]

# מנגנון Earnings Guard חסין אש: מניות בטווח חלון דוחות פעיל (תאריכים קרובים)
ACTIVE_EARNINGS_SEASON = {
    "NVDA": True,   # מדווחת כעת (26 באוגוסט)
    "CRM": True,
    "SNOW": True,
    "CRWD": True
}

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
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        tk = yf.Ticker("^SKEW", session=session)
        df = tk.history(period="5d")
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except Exception as e:
        print(f"Error fetching SKEW: {e}")
    return 130.0

def check_earnings_soon(ticker, ticker_obj):
    """בדיקת דוח קרוב רב-שכבתית (Hardcoded Active Guard + API Fallback)"""
    # 1. בדיקה קשיחה לפי רשימת המניות המדווחות כעת
    if ACTIVE_EARNINGS_SEASON.get(ticker, False):
        return True

    # 2. ניסיון קריאה מ-yfinance במידה והשירות זמין
    try:
        cal = ticker_obj.calendar
        now = datetime.datetime.now()
        earn_dates = []

        if isinstance(cal, dict):
            earn_dates = cal.get('Earnings Date', [])
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            if 'Earnings Date' in cal.index:
                earn_dates = cal.loc['Earnings Date'].tolist()

        for ed in earn_dates:
            ed_dt = None
            if isinstance(ed, (datetime.datetime, datetime.date)):
                ed_dt = datetime.datetime.combine(ed, datetime.time.min) if isinstance(ed, datetime.date) and not isinstance(ed, datetime.datetime) else ed
            elif isinstance(ed, str):
                try:
                    ed_dt = pd.to_datetime(ed).to_pydatetime()
                except Exception:
                    pass

            if ed_dt:
                diff_hours = (ed_dt.replace(tzinfo=None) - now).total_seconds() / 3600
                if -24 <= diff_hours <= 96:
                    return True
    except Exception:
        pass

    return False

def calculate_anchored_vwap(df, anchor_index):
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

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if loss.iloc[-1] != 0 else 50.0

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    recent_low_10 = float(low.iloc[-10:].min())
    entry_limit = round(min(current_price * 0.99, max(recent_low_10, current_price - (0.8 * atr))), 2)

    stop_loss = round(entry_limit - (1.2 * atr), 2)
    risk = entry_limit - stop_loss

    if risk <= 0:
        return None

    recent_high_60 = float(high.iloc[-60:].max())
    target_price = round(max(recent_high_60, entry_limit + (3.0 * risk)), 2)
    reward = target_price - entry_limit

    rr_ratio = round(reward / risk, 2)
    if rr_ratio < 3.0:
        return None

    # זיהוי דוח קרוב (כולל בדיקה ישירה מול NVDA)
    earnings_soon = bool(check_earnings_soon(ticker, tk))

    local_low_idx = df.iloc[-60:]['Low'].idxmin()
    anchor_pos = df.index.get_loc(local_low_idx)
    avwap = calculate_anchored_vwap(df, anchor_pos)
    
    avwap_confluence = bool(abs(entry_limit - avwap) / avwap <= 0.015)

    score = 0
    if current_price > sma150: score += 20
    if current_price > sma50: score += 15
    if 40 <= rsi <= 60: score += 20
    if float(volume.iloc[-1]) > float(volume.iloc[-20:].mean()): score += 15

    if current_skew > 135 and rsi < 50:
        score += 20

    if avwap_confluence:
        score += 25

    # במידה ויש דוח קרוב – הורדה דרסטית של הניקוד כדי למנוע כניסה ל-Top 5
    if earnings_soon:
        score -= 200

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
    print("Scanning stock opportunities with Hardcoded Earnings Guard...")
    current_skew = fetch_skew()

    opportunities = []
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker, current_skew)
        if res:
            opportunities.append(res)
            
    opportunities.sort(key=lambda x: x["score"], reverse=True)
    
    top_5_overall = filter_top5_with_sector_cap(opportunities, max_per_sector=2, max_total=5)
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

    print("Scan complete with Hardcoded Earnings Guard!")

if __name__ == "__main__":
    main()
