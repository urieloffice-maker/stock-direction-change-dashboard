import json
import datetime
import pandas as pd
import yfinance as yf

BENCHMARKS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "QQQ": "QQQ",
    "Russell 2000": "^RUT"
}

def fetch_ticker_data(ticker, period="1y"):
    try:
        df = yf.Ticker(ticker).history(period=period)
        if df.empty:
            return pd.Series(dtype=float)
        # המרה מפורשת של סדרת הנתונים לצירי זמנים ללא אזור זמן (tz-naive) למניעת שגיאות מיזוג
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

def analyze_benchmark(bench_name, bench_ticker, vix_series, rsp_series, xlp_series, xly_series, s5fi_series):
    bench_close = fetch_ticker_data(bench_ticker, period="1y")
    if bench_close.empty:
        return None

    # 1. מרחק מממוצע נע 150 יום
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

    # 2. רוחב שוק - RSP מול המדד
    common_idx = rsp_series.index.intersection(bench_close.index)
    rsp_bench_ratio = (rsp_series.loc[common_idx] / bench_close.loc[common_idx]).dropna()
    trend_rsp = get_trend(rsp_bench_ratio, 20)
    bench_trend = get_trend(bench_close, 20)

    if bench_trend == "עולה" and trend_rsp == "יורד":
        status_rsp, score_rsp, desc_rsp = "סימן אזהרה", 85, "המדד עולה אך רוחב השוק נחלש (Divergence)"
    elif bench_trend == "עולה" and trend_rsp == "עולה":
        status_rsp, score_rsp, desc_rsp = "תקין/בריא", 15, "השתתפות רחבה של מניות השוק בעלייה"
    else:
        status_rsp, score_rsp, desc_rsp = "ניטרלי", 45, "מגמת רוחב שוק ניטרלית"

    # 3. VIX
    current_vix = vix_series.iloc[-1] if not vix_series.empty else 15.0
    vix_trend = get_trend(vix_series, 10)
    if current_vix < 14:
        status_vix, score_vix, desc_vix = "סימן אזהרה", 75, "שאננות יתר בשוק (VIX נמוך מאוד)"
    elif 14 <= current_vix <= 20:
        status_vix, score_vix, desc_vix = "ניטרלי", 30, "רמת תנודתיות סבירה וניטרלית"
    else:
        status_vix, score_vix, desc_vix = "סימן אזהרה", 65, "פחד ותנודתיות מוגברת בשוק"

    # 4. רוטציה הגנתית XLP / המדד
    common_xlp_idx = xlp_series.index.intersection(bench_close.index)
    xlp_bench_ratio = (xlp_series.loc[common_xlp_idx] / bench_close.loc[common_xlp_idx]).dropna()
    trend_xlp_20 = get_trend(xlp_bench_ratio, 20)
    trend_xlp_50 = get_trend(xlp_bench_ratio, 50)
    trend_xlp_100 = get_trend(xlp_bench_ratio, 100)

    if trend_xlp_20 == "עולה":
        status_xlp, score_xlp, desc_xlp = "סימן אזהרה", 80, "מעבר כסף לסקטורים הגנתיים (XLP)"
    else:
        status_xlp, score_xlp, desc_xlp = "תקין/בריא", 20, "העדפת נכסי סיכון על פני סקטורים הגנתיים"

    # 5. תיאבון לסיכון XLY / XLP
    common_xly_idx = xly_series.index.intersection(xlp_series.index)
    xly_xlp_ratio = (xly_series.loc[common_xly_idx] / xlp_series.loc[common_xly_idx]).dropna()
    trend_risk_appetite = get_trend(xly_xlp_ratio, 20)
    if trend_risk_appetite == "יורד":
        status_risk, score_risk, desc_risk = "סימן אזהרה", 75, "ירידה בתיאבון לסיכון, העדפת צריכה בסיסית"
    else:
        status_risk, score_risk, desc_risk = "תקין/בריא", 20, "תיאבון סיכון בריא, העדפת צריכה מחזורית"

    # 6. S5FI - אחוז מניות מעל ממוצע 50
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

    # ציון סיכון משוקלל
    weighted_score = round(
        score_sma * 0.25 +
        score_rsp * 0.25 +
        score_s5fi * 0.20 +
        score_xlp * 0.15 +
        score_vix * 0.075 +
        score_risk * 0.075, 1
    )

    if weighted_score <= 30:
        overall_status = "סיכון נמוך"
        conclusion = "השוק במצב בריא וחזק, לא נצפות אינדיקציות קריטיות לתיקון בטווח הקצר."
    elif weighted_score <= 50:
        overall_status = "סיכון מתון"
        conclusion = "השוק במצב תקין אך יש לעקוב מקרוב אחר סקטורים נחלשים."
    elif weighted_score <= 70:
        overall_status = "סיכון גבוה"
        conclusion = "השוק מתוח ונצפים סימני אזהרה ברוחב השוק/רוטציה הגנתית. מומלץ לנהל סיכונים."
    else:
        overall_status = "סיכון גבוה מאוד לתיקון"
        conclusion = "השוק נמצא במתיחת-יתר עמוקה או בחולשה פנימית חריפה. הסבירות לתיקון בטווח הקצר גבוהה מאוד."

    rsp_chart = []
    for d in rsp_bench_ratio.index[-120:]:
        rsp_chart.append({
            "date": d.strftime("%Y-%m-%d"),
            "ratio": round(float(rsp_bench_ratio.loc[d]), 4)
        })

    return {
        "weighted_risk_score": weighted_score,
        "overall_status": overall_status,
        "conclusion": conclusion,
        "rsp_chart": rsp_chart,
        "indicators": [
            {
                "name": "מרחק מממוצע נע 150 יום",
                "val": f"{dist_sma150:.2f}%",
                "trend": trend_sma,
                "status": status_sma,
                "score": score_sma,
                "desc": desc_sma
            },
            {
                "name": "רוחב שוק (RSP מול מדד)",
                "val": f"{rsp_bench_ratio.iloc[-1]:.4f}" if not rsp_bench_ratio.empty else "N/A",
                "trend": trend_rsp,
                "status": status_rsp,
                "score": score_rsp,
                "desc": desc_rsp
            },
            {
                "name": "סנטימנט ופחד (VIX)",
                "val": f"{current_vix:.2f}",
                "trend": vix_trend,
                "status": status_vix,
                "score": score_vix,
                "desc": desc_vix
            },
            {
                "name": "רוטציה הגנתית (XLP / המדד)",
                "val": f"20d: {trend_xlp_20} | 50d: {trend_xlp_50} | 100d: {trend_xlp_100}",
                "trend": trend_xlp_20,
                "status": status_xlp,
                "score": score_xlp,
                "desc": desc_xlp
            },
            {
                "name": "תיאבון לסיכון (XLY / XLP)",
                "val": f"{xly_xlp_ratio.iloc[-1]:.3f}" if not xly_xlp_ratio.empty else "N/A",
                "trend": trend_risk_appetite,
                "status": status_risk,
                "score": score_risk,
                "desc": desc_risk
            },
            {
                "name": "S5FI (% מניות מעל ממוצע 50)",
                "val": f"{current_s5fi:.1f}%",
                "trend": s5fi_trend,
                "status": status_s5fi,
                "score": score_s5fi,
                "desc": desc_s5fi
            }
        ]
    }

def main():
    print("Fetching global market indicators...")
    vix_series = fetch_ticker_data("^VIX")
    rsp_series = fetch_ticker_data("RSP")
    xlp_series = fetch_ticker_data("XLP")
    xly_series = fetch_ticker_data("XLY")
    
    s5fi_series = fetch_ticker_data("^S5FI")
    if s5fi_series.empty:
        spy_series = fetch_ticker_data("SPY")
        common = rsp_series.index.intersection(spy_series.index)
        s5fi_series = (rsp_series.loc[common] / spy_series.loc[common]) * 100

    output = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "benchmarks": {}
    }

    for name, ticker in BENCHMARKS.items():
        print(f"Analyzing {name}...")
        res = analyze_benchmark(name, ticker, vix_series, rsp_series, xlp_series, xly_series, s5fi_series)
        if res:
            output["benchmarks"][name] = res

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("data.json updated successfully!")

if __name__ == "__main__":
    main()
