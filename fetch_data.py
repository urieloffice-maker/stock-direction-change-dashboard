import json
import datetime
import os
import time
import urllib.request
import urllib.parse
import pandas as pd
import yfinance as yf

BENCHMARKS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "QQQ": "QQQ",
    "Russell 2000": "^RUT"
}

SECTORS = {
    "טכנולוגיה (XLK)": "XLK",
    "פיננסים (XLF)": "XLF",
    "בריאות (XLV)": "XLV",
    "צריכה מחזורית (XLY)": "XLY",
    "תקשורת (XLC)": "XLC",
    "תעשייה (XLI)": "XLI",
    "צריכה בסיסית (XLP)": "XLP",
    "אנרגיה (XLE)": "XLE",
    "תשתיות (XLU)": "XLU",
    "חומרים (XLB)": "XLB",
    "נדל״ן (XLRE)": "XLRE"
}

def fetch_ticker_data(ticker, period="1y"):
    try:
        df = yf.Ticker(ticker).history(period=period)
        if df.empty:
            return pd.Series(dtype=float)
        series = df['Close']
        series.index = series.index.tz_localize(None)
        return series
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return pd.Series(dtype=float)

def calculate_sma(series, window):
    return series.rolling(window=window).mean()

def get_trend(series, window=20):
    series = series.dropna()
    if len(series) < window:
        return "ניטרלי"
    diff = series.iloc[-1] - series.iloc[-window]
    if diff > 0.005 * series.iloc[-window]:
        return "עולה"
    elif diff < -0.005 * series.iloc[-window]:
        return "יורד"
    return "ניטרלי"

def check_bearish_divergence(price_series, breadth_series, window=20):
    price_s = price_series.dropna()
    breadth_s = breadth_series.dropna()
    common = price_s.index.intersection(breadth_s.index)
    if len(common) < window:
        return False
    
    price_sub = price_s.loc[common].iloc[-window:]
    breadth_sub = breadth_s.loc[common].iloc[-window:]
    
    price_making_highs = price_sub.iloc[-1] >= price_sub.max() * 0.99
    breadth_failing = breadth_sub.iloc[-1] < breadth_sub.max() * 0.95
    
    return bool(price_making_highs and breadth_failing)

def analyze_sectors():
    sector_results = []
    print("Fetching sector data via bulk download...")
    tickers_list = list(SECTORS.values())
    
    try:
        df_bulk = yf.download(tickers_list, period="3m", progress=False)
        
        # טיפול מפורש במבנה MultiIndex של yfinance
        if isinstance(df_bulk.columns, pd.MultiIndex):
            if 'Close' in df_bulk.columns.levels[0]:
                close_df = df_bulk['Close']
            elif 'Close' in df_bulk.columns.levels[1]:
                close_df = df_bulk.xs('Close', axis=1, level=1)
            else:
                close_df = df_bulk
        else:
            close_df = df_bulk

        for name, ticker in SECTORS.items():
            if ticker in close_df.columns:
                s = close_df[ticker].dropna()
                if not s.empty and len(s) >= 5:
                    win = min(20, len(s))
                    ret_20d = ((s.iloc[-1] - s.iloc[-win]) / s.iloc[-win]) * 100
                    trend = get_trend(s, win)
                    sector_results.append({
                        "name": name,
                        "ticker": ticker,
                        "return_20d": round(float(ret_20d), 2),
                        "trend": trend,
                        "status": "חזק" if ret_20d > 1 else ("נחלש/חלש" if ret_20d < -1 else "ניטרלי")
                    })
    except Exception as e:
        print(f"Bulk download failed with error: {e}")

    # מנגנון גיבוי במידה וההורדה המקובצת החזירה נתונים חסרים
    if len(sector_results) < len(SECTORS):
        print("Fallback: Fetching missing sectors individually...")
        existing_tickers = {s["ticker"] for s in sector_results}
        for name, ticker in SECTORS.items():
            if ticker not in existing_tickers:
                s = fetch_ticker_data(ticker, period="3m")
                if not s.empty and len(s) >= 5:
                    win = min(20, len(s))
                    ret_20d = ((s.iloc[-1] - s.iloc[-win]) / s.iloc[-win]) * 100
                    trend = get_trend(s, win)
                    sector_results.append({
                        "name": name,
                        "ticker": ticker,
                        "return_20d": round(float(ret_20d), 2),
                        "trend": trend,
                        "status": "חזק" if ret_20d > 1 else ("נחלש/חלש" if ret_20d < -1 else "ניטרלי")
                    })
                time.sleep(0.2)

    sector_results.sort(key=lambda x: x["return_20d"], reverse=True)
    print(f"Processed {len(sector_results)} sectors successfully.")
    return sector_results

def send_telegram_alert(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req)
        print("Telegram alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def load_previous_history():
    if os.path.exists("data.json"):
        try:
            with open("data.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                return old_data.get("history", {})
        except Exception:
            return {}
    return {}

def analyze_benchmark(bench_name, bench_ticker, vix_series, rsp_series, xlp_series, xly_series, s5fi_series, pcc_series, sector_data, history_data):
    bench_close = fetch_ticker_data(bench_ticker, period="1y")
    if bench_close.empty:
        return None

    sma150 = calculate_sma(bench_close, 150)
    current_price = bench_close.iloc[-1]
    current_sma150 = sma150.iloc[-1] if not pd.isna(sma150.iloc[-1]) else current_price
    dist_sma150 = ((current_price - current_sma150) / current_sma150) * 100

    if dist_sma150 >= 15:
        status_sma, score_sma, desc_sma = "סימן אזהרה", 90, "מתיחת-יתר משמעותית מעל ממוצע 150 יום"
    elif dist_sma150 >= 10:
        status_sma, score_sma, desc_sma = "סימן אזהרה", 70, "התחלת אזהרה, מרחק גבוה מהממוצע הנע"
    else:
        status_sma, score_sma, desc_sma = "תקין/בריא", 20, "מרחק בריא ותקין מהממוצע הנע 150 יום"

    trend_sma = "עולה" if dist_sma150 > 0 else "יורד"

    common_idx = rsp_series.index.intersection(bench_close.index)
    rsp_bench_ratio = (rsp_series.loc[common_idx] / bench_close.loc[common_idx]).dropna()
    trend_rsp = get_trend(rsp_bench_ratio, 20)
    bench_trend = get_trend(bench_close, 20)

    is_divergent = check_bearish_divergence(bench_close, rsp_bench_ratio, 20)

    if is_divergent or (bench_trend == "עולה" and trend_rsp == "יורד"):
        status_rsp, score_rsp = "סימן אזהרה", 90
        desc_rsp = "זיהוי סטייה שלילית חריפה! המדד בשיא אך רוחב השוק נחלש" if is_divergent else "המדד עולה אך רוחב השוק נחלש"
    elif bench_trend == "עולה" and trend_rsp == "עולה":
        status_rsp, score_rsp, desc_rsp = "תקין/בריא", 15, "השתתפות רחבה של מניות השוק בעלייה"
    else:
        status_rsp, score_rsp, desc_rsp = "ניטרלי", 45, "מגמת רוחב שוק ניטרלית"

    current_vix = vix_series.iloc[-1] if not vix_series.empty else 15.0
    vix_trend = get_trend(vix_series, 10)
    if current_vix < 14:
        status_vix, score_vix, desc_vix = "סימן אזהרה", 75, "שאננות יתר בשוק (VIX נמוך מאוד)"
    elif 14 <= current_vix <= 20:
        status_vix, score_vix, desc_vix = "ניטרלי", 30, "רמת תנודתיות סבירה וניטרלית"
    else:
        status_vix, score_vix, desc_vix = "סימן אזהרה", 65, "פחד ותנודתיות מוגברת בשוק"

    current_pcc = pcc_series.iloc[-1] if not pcc_series.empty else 0.85
    pcc_trend = get_trend(pcc_series, 10)
    if current_pcc < 0.70:
        status_pcc, score_pcc, desc_pcc = "סימן אזהרה", 80, "שאננות בשוק הנגזרים (Put/Call נמוך)"
    elif 0.70 <= current_pcc <= 1.05:
        status_pcc, score_pcc, desc_pcc = "תקין/בריא", 25, "סנטימנט נורמלי בשוק הנגזרים"
    else:
        status_pcc, score_pcc, desc_pcc = "סימן אזהרה", 60, "חששות מוגברים ורכישת הגנות מאסיבית"

    common_xlp_idx = xlp_series.index.intersection(bench_close.index)
    xlp_bench_ratio = (xlp_series.loc[common_xlp_idx] / bench_close.loc[common_xlp_idx]).dropna()
    trend_xlp_20 = get_trend(xlp_bench_ratio, 20)
    trend_xlp_50 = get_trend(xlp_bench_ratio, 50)
    trend_xlp_100 = get_trend(xlp_bench_ratio, 100)

    if trend_xlp_20 == "עולה":
        status_xlp, score_xlp, desc_xlp = "סימן אזהרה", 80, "מעבר כסף לסקטורים הגנתיים (XLP)"
    else:
        status_xlp, score_xlp, desc_xlp = "תקין/בריא", 20, "העדפת נכסי סיכון על פני סקטורים הגנתיים"

    common_xly_idx = xly_series.index.intersection(xlp_series.index)
    xly_xlp_ratio = (xly_series.loc[common_xly_idx] / xlp_series.loc[common_xly_idx]).dropna()
    trend_risk_appetite = get_trend(xly_xlp_ratio, 20)
    if trend_risk_appetite == "יורד":
        status_risk, score_risk, desc_risk = "סימן אזהרה", 75, "ירידה בתיאבון לסיכון, העדפת צריכה בסיסית"
    else:
        status_risk, score_risk, desc_risk = "תקין/בריא", 20, "תיאבון סיכון בריא, העדפת צריכה מחזורית"

    current_s5fi = s5fi_series.iloc[-1] if not s5fi_series.empty else 60.0
    s5fi_trend = get_trend(s5fi_series, 10)
    if current_s5fi > 70:
        status_s5fi, score_s5fi, desc_s5fi = "סימן אזהרה", 80, "שוק חם/מתוח יתר על המידה"
    elif 50 <= current_s5fi <= 70:
        status_s5fi, score_s5fi, desc_s5fi = "תקין/בריא", 25, "מצב רוחב שוק חיובי ובריא"
    elif 30 <= current_s5fi < 50:
        status_s5fi, score_s5fi, desc_s5fi = "ניטרלי", 55, "חולשה פנימית ברוחב השוק"
    else:
        status_s5fi, score_s5fi, desc_s5fi = "סימן אזהרה", 85, "מכירות-יתר או חולשה פנימית עמוקה"

    weighted_score = round(
        score_sma * 0.20 + score_rsp * 0.25 + score_s5fi * 0.20 +
        score_xlp * 0.15 + score_vix * 0.05 + score_pcc * 0.05 + score_risk * 0.10, 1
    )

    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    bench_hist = history_data.get(bench_name, [])
    
    if len(bench_hist) <= 1:
        bench_hist = []
        for i in range(5, 0, -1):
            d = (datetime.datetime.utcnow() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            bench_hist.append({"date": d, "score": weighted_score})
            
    bench_hist = [h for h in bench_hist if h["date"] != today_str]
    bench_hist.append({"date": today_str, "score": weighted_score})
    bench_hist = bench_hist[-30:]

    weak_sectors = [s["name"] for s in sector_data if s["status"] == "נחלש/חלש"]
    if weak_sectors:
        target_sectors_str = ", ".join(weak_sectors)
    elif len(sector_data) >= 2:
        target_sectors_str = f"{sector_data[-1]['name']} ({sector_data[-1]['return_20d']}%) ו-{sector_data[-2]['name']} ({sector_data[-2]['return_20d']}%)"
    else:
        target_sectors_str = "סקטורים בפיגור יחסי"

    divergence_msg = " ⚠️ **זוהתה סטייה שלילית (Bearish Divergence) בין המדד לרוחב השוק!**" if is_divergent else ""

    if weighted_score <= 30:
        overall_status = "סיכון נמוך"
        conclusion = f"השוק במצב בריא וחזק.{divergence_msg} סקטורים בפיגור יחסי למעקב: {target_sectors_str}."
    elif weighted_score <= 50:
        overall_status = "סיכון מתון"
        conclusion = f"השוק במצב תקין אך דורש מעקב.{divergence_msg} מומלץ לעקוב מקרוב אחר הסקטורים החלשים/בפיגור: {target_sectors_str}."
    elif weighted_score <= 70:
        overall_status = "סיכון גבוה"
        conclusion = f"השוק מתוח ונצפים סימני אזהרה.{divergence_msg} מומלץ לצמצם חשיפה בסקטורים החלשים/בפיגור: {target_sectors_str}."
    else:
        overall_status = "סיכון גבוה מאוד לתיקון"
        conclusion = f"הסבירות לתיקון בטווח הקצר גבוהה מאוד.{divergence_msg} מומלץ לצמצם חשיפה מיידית בסקטורים החלשים: {target_sectors_str}."

    if bench_name == "S&P 500" and weighted_score >= 70:
        send_telegram_alert(f"🚨 *התראת סיכון גבוה בשוק ההון!*\n\nציון הסיכון המשוקלל ב-S&P 500 הגיע ל-*{weighted_score}/100* ({overall_status}).\n\n{conclusion}")

    rsp_chart = [{"date": d.strftime("%Y-%m-%d"), "ratio": round(float(rsp_bench_ratio.loc[d]), 4)} for d in rsp_bench_ratio.index[-120:]]

    return {
        "weighted_risk_score": weighted_score,
        "overall_status": overall_status,
        "conclusion": conclusion,
        "is_divergent": is_divergent,
        "history": bench_hist,
        "rsp_chart": rsp_chart,
        "sectors": sector_data,
        "indicators": [
            {"name": "מרחק מממוצע נע 150 יום", "val": f"{dist_sma150:.2f}%", "trend": trend_sma, "status": status_sma, "score": score_sma, "desc": desc_sma},
            {"name": "רוחב שוק (RSP מול מדד)", "val": f"{rsp_bench_ratio.iloc[-1]:.4f}" if not rsp_bench_ratio.empty else "N/A", "trend": trend_rsp, "status": status_rsp, "score": score_rsp, "desc": desc_rsp},
            {"name": "סנטימנט ופחד (VIX)", "val": f"{current_vix:.2f}", "trend": vix_trend, "status": status_vix, "score": score_vix, "desc": desc_vix},
            {"name": "יחס אופציות (Put/Call Ratio)", "val": f"{current_pcc:.2f}", "trend": pcc_trend, "status": status_pcc, "score": score_pcc, "desc": desc_pcc},
            {"name": "רוטציה הגנתית (XLP / המדד)", "val": f"20d: {trend_xlp_20} | 50d: {trend_xlp_50} | 100d: {trend_xlp_100}", "trend": trend_xlp_20, "status": status_xlp, "score": score_xlp, "desc": desc_xlp},
            {"name": "תיאבון לסיכון (XLY / XLP)", "val": f"{xly_xlp_ratio.iloc[-1]:.3f}" if not xly_xlp_ratio.empty else "N/A", "trend": trend_risk_appetite, "status": status_risk, "score": score_risk, "desc": desc_risk},
            {"name": "S5FI (% מניות מעל ממוצע 50)", "val": f"{current_s5fi:.1f}%", "trend": s5fi_trend, "status": status_s5fi, "score": score_s5fi, "desc": desc_s5fi}
        ]
    }

def main():
    print("Fetching market & sector indicators...")
    vix_series = fetch_ticker_data("^VIX")
    rsp_series = fetch_ticker_data("RSP")
    xlp_series = fetch_ticker_data("XLP")
    xly_series = fetch_ticker_data("XLY")
    pcc_series = fetch_ticker_data("^PCC")
    if pcc_series.empty:
        pcc_series = pd.Series([0.85] * len(vix_series), index=vix_series.index)
    
    s5fi_series = fetch_ticker_data("^S5FI")
    if s5fi_series.empty:
        spy_series = fetch_ticker_data("SPY")
        common = rsp_series.index.intersection(spy_series.index)
        s5fi_series = (rsp_series.loc[common] / spy_series.loc[common]) * 100

    sector_data = analyze_sectors()
    history_data = load_previous_history()

    output = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "global_sectors": sector_data,
        "history": history_data,
        "benchmarks": {}
    }

    for name, ticker in BENCHMARKS.items():
        res = analyze_benchmark(name, ticker, vix_series, rsp_series, xlp_series, xly_series, s5fi_series, pcc_series, sector_data, history_data)
        if res:
            output["benchmarks"][name] = res
            output["history"][name] = res["history"]

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("Data updated successfully!")

if __name__ == "__main__":
    main()
