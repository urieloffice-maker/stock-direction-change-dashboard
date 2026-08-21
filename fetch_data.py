import json
import datetime
import pandas as pd
import yfinance as yf

# הגדרת מדדי הייחוס למעקב
BENCHMARKS = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "QQQ": "QQQ",
    "Russell 2000": "^RUT"
}

def calculate_metrics(df):
    """חישוב תשואה מצטברת ו-Drawdown"""
    df['Cumulative Return'] = (1 + df['Close'].pct_change().fillna(0)).cumprod() - 1
    df['Peak'] = df['Close'].cummax()
    df['Drawdown'] = (df['Close'] - df['Peak']) / df['Peak']
    return df

def fetch_all_data():
    output_data = {
        "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "benchmarks": {}
    }
    
    for name, ticker in BENCHMARKS.items():
        print(f"Fetching data for {name} ({ticker})...")
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="1y")
        
        if df.empty:
            continue
            
        df = calculate_metrics(df)
        
        records = []
        for index, row in df.iterrows():
            records.append({
                "date": index.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
                "cum_return": round(float(row["Cumulative Return"]) * 100, 2),
                "drawdown": round(float(row["Drawdown"]) * 100, 2)
            })
            
        output_data["benchmarks"][name] = records

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print("data.json updated successfully!")

if __name__ == "__main__":
    fetch_all_data()
