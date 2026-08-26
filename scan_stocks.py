import json
import os
import datetime
import urllib.request
import urllib.parse
import requests
import math
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

ACTIVE_EARNINGS_SEASON = {
    "NVDA": True,
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

RISK_PER_TRADE = 200.0  # ניהול סיכון של $200 לעסקה

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

def fetch_spy_perf_20d():
    """שליפת תשואת SPY ב-20 ימי המסחר האחרונים לצורך חישוב RS"""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        spy = yf.Ticker("SPY", session=session)
        df = spy.history(period="3mo")
        if not df.empty and len(df) >= 20:
            c = df['Close']
            perf = ((c.iloc[-1] - c.iloc[-20]) / c.iloc[-20]) * 100
            return float(perf)
    except Exception as e:
        print(f"Error fetching SPY perf: {e}")
    return 0.0

def check_earnings_soon(ticker, ticker_obj):
    if ACTIVE_EARNINGS_SEASON.get(ticker, False):
        return True
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
        vwap_tag = " 🎯 *AVWAP*" if item['avwap_confluence'] else ""
        rs_tag = " 🚀 *RS Leader*" if item['rs_leader'] else ""
        fib_tag = " 🌟 *Golden Fib*" if item['golden_fib_confluence'] else ""
        
        tv_link = f"[TradingView](https://www.tradingview.com/symbols/{item['ticker']})"
        yf_link = f"[Yahoo](https://finance.yahoo.com/quote/{item['ticker']})"
        
        message += (
            f"📌 *{item['ticker']}* ({item['sector']}){earn_tag}{vwap_tag}{rs_tag}{fib_tag}\n"
            f"💵 נוכחי: `${item['current_price']}` | 🟢 **Limit:** `${item['entry_limit']}`\n"
            f"🔴 **Stop:** `${item['stop_loss']}` | 🎯 **Target:** `${item['target_price']}` (1:{item['rr_ratio']})\n"
            f"📦 **כמות מניות:** `{item['share_size']}` מניות | 💰 **שווי פוזיציה:** `${item['position_value']}`\n"
            f"🔗 קישורים: {tv_link} | {yf_link}\n"
            f"-----------------------------------\n"
        )

    message += "\n🌐 *המניה המובילה מכל סקטור (Best Per Sector)*\n\n"
    for item in best_per_sector:
        earn_tag = " ⚠️ *EARNINGS SOON*" if item['earnings_soon'] else ""
        tv_link = f"[TradingView](https://www.tradingview.com/symbols/{item['ticker']})"
        message += (
            f"🏢 *{item['sector']}: {item['ticker']}*{earn_tag}\n"
            f"🟢 **Limit:** `${item['entry_limit']}` | 🔴 **Stop:** `${item['stop_loss']}` | 🎯 **Target:** `${item['target_price']}` (1:{item['rr_ratio']})\n"
            f"📦 **כמות מניות:** `{item['share_size']}` | 🔗 {tv_link}\n"
            f"-----------------------------------\n"
        )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, 
        "text": message, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
        print("Telegram dual opportunities alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def scan_opportunity(ticker, current_skew, spy_perf_20d):
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
    risk_per_share = entry_limit - stop_loss

    if risk_per_share <= 0:
        return None

    recent_high_60 = float(high.iloc[-60:].max())
    target_price = round(max(recent_high_60, entry_limit + (3.0 * risk_per_share)), 2)
    reward = target_price - entry_limit

    rr_ratio = round(reward / risk_per_share, 2)
    if rr_ratio < 3.0:
        return None

    # שדרוג 5: מחשבון גודל פוזיציה לפי סיכון של $200
    share_size = int(math.floor(RISK_PER_TRADE / risk_per_share)) if risk_per_share > 0 else 0
    position_value = round(share_size * entry_limit, 2)

    # שדרוג 1: עוצמה יחסית מול SPY ב-20 יום
    stock_perf_20d = float(((current_price - close.iloc[-20]) / close.iloc[-20]) * 100)
    relative_strength = round(stock_perf_20d - spy_perf_20d, 2)
    rs_leader = bool(relative_strength > 0)

    # שדרוג 2: ניתוח נפח מסחר ב-Pullback (Volume & Accumulation Guard)
    vol_2d_avg = float(volume.iloc[-2:].mean())
    vol_20d_avg = float(volume.iloc[-20:].mean())
    healthy_pullback_vol = bool(rsi < 55 and vol_2d_avg < vol_20d_avg)

    # שדרוג 3: אזור פיבונאצ'י מוזהב (50% - 61.8%)
    recent_low_60 = float(low.iloc[-60:].min())
    range_60 = recent_high_60 - recent_low_60
    fib_50 = recent_high_60 - (0.50 * range_60)
    fib_618 = recent_high_60 - (0.618 * range_60)
    fib_golden_high = max(fib_50, fib_618)
    fib_golden_low = min(fib_50, fib_618)
    golden_fib_confluence = bool(fib_golden_low * 0.985 <= entry_limit <= fib_golden_high * 1.015)

    earnings_soon = bool(check_earnings_soon(ticker, tk))

    local_low_idx = df.iloc[-60:]['Low'].idxmin()
    anchor_pos = df.index.get_loc(local_low_idx)
    avwap = calculate_anchored_vwap(df, anchor_pos)
    avwap_confluence = bool(abs(entry_limit - avwap) / avwap <= 0.015)

    score = 0
    if current_price > sma150: score += 15
    if current_price > sma50: score += 10
    if 40 <= rsi <= 60: score += 15
    if vol_20d_avg > 0 and volume.iloc[-1] > vol_20d_avg: score += 10

    if rs_leader: score += 15
    if healthy_pullback_vol: score += 15
    if golden_fib_confluence: score += 20
    if current_skew > 135 and rsi < 50: score += 15
    if avwap_confluence: score += 20

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
        "share_size": share_size,
        "position_value": position_value,
        "relative_strength": relative_strength,
        "rs_leader": rs_leader,
        "healthy_pullback_vol": healthy_pullback_vol,
        "golden_fib_confluence": golden_fib_confluence,
        "rsi": round(rsi, 1),
        "avwap": round(avwap, 2),
        "avwap_confluence": avwap_confluence,
        "earnings_soon": earnings_soon,
        "score": score
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

# שדרוג 4: מערכת מעקב אחר ביצועי עסקאות היסטוריות (Forward Tracking System)
def update_forward_tracking(new_top_5, existing_data):
    tracking_history = existing_data.get("forward_tracking", [])
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    # 1. סקירת העסקאות הפעילות הקיימות ועדכון סטטוס לפי מחירים מעודכנים
    for trade in tracking_history:
        if trade["status"] == "PENDING":
            try:
                session = requests.Session()
                session.headers.update(HEADERS)
                tk = yf.Ticker(trade["ticker"], session=session)
                hist = tk.history(period="10d")
                if not hist.empty:
                    recent_low = float(hist['Low'].min())
                    recent_high = float(hist['High'].max())

                    if recent_low <= trade["entry_limit"]:
                        trade["status"] = "FILLED"
                        trade["filled_date"] = today_str

            except Exception as e:
                print(f"Error checking tracking for {trade['ticker']}: {e}")

        elif trade["status"] == "FILLED":
            try:
                session = requests.Session()
                session.headers.update(HEADERS)
                tk = yf.Ticker(trade["ticker"], session=session)
                hist = tk.history(period="10d")
                if not hist.empty:
                    recent_low = float(hist['Low'].min())
                    recent_high = float(hist['High'].max())

                    if recent_high >= trade["target_price"]:
                        trade["status"] = "WIN"
                        trade["closed_date"] = today_str
                    elif recent_low <= trade["stop_loss"]:
                        trade["status"] = "LOSS"
                        trade["closed_date"] = today_str
            except Exception as e:
                print(f"Error checking status for {trade['ticker']}: {e}")

    # 2. הוספת פקודות חדשות מ-Top 5 של היום (במידה ולא קיימות)
    existing_keys = {f"{t['ticker']}_{t['created_date']}" for t in tracking_history}
    for item in new_top_5:
        key = f"{item['ticker']}_{today_str}"
        if key not in existing_keys:
            tracking_history.append({
                "ticker": item["ticker"],
                "sector": item["sector"],
                "created_date": today_str,
                "entry_limit": item["entry_limit"],
                "stop_loss": item["stop_loss"],
                "target_price": item["target_price"],
                "rr_ratio": item["rr_ratio"],
                "status": "PENDING"
            })

    # חישוב אחוז הצלחה
    closed_trades = [t for t in tracking_history if t["status"] in ["WIN", "LOSS"]]
    wins = [t for t in closed_trades if t["status"] == "WIN"]
    win_rate = round((len(wins) / len(closed_trades)) * 100, 1) if closed_trades else 0.0

    return tracking_history[-50:], win_rate  # שמירת 50 עסקאות אחרונות

def main():
    print("Scanning stock opportunities with 6 New Upgrades...")
    current_skew = fetch_skew()
    spy_perf_20d = fetch_spy_perf_20d()

    opportunities = []
    for ticker in WATCHLIST:
        res = scan_opportunity(ticker, current_skew, spy_perf_20d)
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

    forward_tracking, win_rate = update_forward_tracking(top_5_overall, data)

    data["stock_opportunities"] = top_5_overall
    data["best_per_sector_opportunities"] = best_per_sector
    data["skew_index"] = current_skew
    data["forward_tracking"] = forward_tracking
    data["win_rate"] = win_rate

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    send_telegram_opportunities(top_5_overall, best_per_sector)

    print("Scan complete with full 6 upgrades!")

if __name__ == "__main__":
    main()
