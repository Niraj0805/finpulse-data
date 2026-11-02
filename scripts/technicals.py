"""
FinPulse technicals engine.
Runs on GitHub Actions after NSE close. Downloads ~1.5y of daily prices (free, via yfinance)
for the Nifty 200 + any symbols in config/symbols.txt, computes indicators, and writes:
  data/technicals.json   - latest indicator snapshot per symbol
  data/closes.json       - last ~400 daily closes per symbol (for scoreboard grading)
  data/market.json       - index levels and 1d/1m/3m/6m returns
"""
import json, os, io, datetime as dt
import numpy as np, pandas as pd, requests, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data"); os.makedirs(DATA, exist_ok=True)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

NIFTY50_FALLBACK = """ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL
CIPLA COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDUNILVR ICICIBANK
INDUSINDBK INFY ITC JIOFIN JSWSTEEL KOTAKBANK LT M&M MARUTI NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE SBIN
SHRIRAMFIN SUNPHARMA TATACONSUM TATAMOTORS TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO""".split()

INDICES = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "NIFTY BANK": "^NSEBANK", "NIFTY IT": "^CNXIT",
           "INDIA VIX": "^INDIAVIX", "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "USD/INR": "INR=X",
           "BRENT": "BZ=F", "GOLD": "GC=F", "US 10Y": "^TNX"}


def universe():
    syms = []
    try:
        r = requests.get("https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        syms = [s.strip() for s in df["Symbol"].tolist()]
    except Exception as e:
        print("Nifty 200 list unavailable, using Nifty 50 fallback:", e)
        syms = NIFTY50_FALLBACK
    extra = os.path.join(ROOT, "config", "symbols.txt")
    if os.path.exists(extra):
        for line in open(extra):
            s = line.split("#")[0].strip().upper()
            if s and s not in syms:
                syms.append(s)
    return syms


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def pivots(h, l, win=5, look=120):
    """Recent swing highs/lows as resistance/support candidates."""
    h, l = h.tail(look), l.tail(look)
    hi = h[(h == h.rolling(win * 2 + 1, center=True).max())].dropna()
    lo = l[(l == l.rolling(win * 2 + 1, center=True).min())].dropna()
    return hi, lo


def analyse(df):
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    if len(c) < 60:
        return None
    last = float(c.iloc[-1])
    sma20, sma50 = c.rolling(20).mean(), c.rolling(50).mean()
    sma200 = c.rolling(200).mean() if len(c) >= 200 else pd.Series([np.nan] * len(c), index=c.index)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26; sig = macd.ewm(span=9, adjust=False).mean(); hist = macd - sig
    r = rsi(c)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    vol20 = v.rolling(20).mean()
    hi, lo = pivots(h, l)
    supports = sorted({round(float(x), 1) for x in lo if x < last}, reverse=True)[:2]
    resist = sorted({round(float(x), 1) for x in hi if x > last})[:2]
    hi52, lo52 = float(h.tail(252).max()), float(l.tail(252).min())
    s50, s200 = float(sma50.iloc[-1]), float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

    # trend classification
    if s200 and last > s50 > s200:
        trend = "Uptrend"
    elif s200 and last < s50 < s200:
        trend = "Downtrend"
    else:
        trend = "Sideways"
    golden = bool(s200 and sma50.iloc[-1] > sma200.iloc[-1] and sma50.iloc[-6] <= sma200.iloc[-6])
    death = bool(s200 and sma50.iloc[-1] < sma200.iloc[-1] and sma50.iloc[-6] >= sma200.iloc[-6])
    macd_cross = "bullish crossover" if hist.iloc[-1] > 0 >= hist.iloc[-2] else \
                 "bearish crossover" if hist.iloc[-1] < 0 <= hist.iloc[-2] else \
                 ("above signal" if hist.iloc[-1] > 0 else "below signal")
    vol_ratio = float(v.iloc[-1] / vol20.iloc[-1]) if vol20.iloc[-1] else None
    breakout = bool(last >= float(h.tail(55).iloc[:-1].max()) and (vol_ratio or 0) > 1.5)
    breakdown = bool(last <= float(l.tail(55).iloc[:-1].min()) and (vol_ratio or 0) > 1.5)

    setup = []
    if breakout: setup.append("55-day breakout on volume")
    if breakdown: setup.append("55-day breakdown on volume")
    if golden: setup.append("golden cross")
    if death: setup.append("death cross")
    rv = float(r.iloc[-1])
    if rv >= 70: setup.append("overbought")
    if rv <= 30: setup.append("oversold")

    def ret(n):
        return round((last / float(c.iloc[-n - 1]) - 1) * 100, 2) if len(c) > n else None

    return {
        "close": round(last, 2), "asOf": str(c.index[-1].date()),
        "chg1d": ret(1), "ret1m": ret(21), "ret3m": ret(63), "ret6m": ret(126), "ret1y": ret(250),
        "rsi": round(rv, 1), "macd": round(float(macd.iloc[-1]), 2), "macdSignal": round(float(sig.iloc[-1]), 2),
        "macdState": macd_cross, "dma20": round(float(sma20.iloc[-1]), 1), "dma50": round(s50, 1),
        "dma200": round(s200, 1) if s200 else None, "trend": trend, "atr": round(float(atr.iloc[-1]), 2),
        "atrPct": round(float(atr.iloc[-1]) / last * 100, 2), "volRatio": round(vol_ratio, 2) if vol_ratio else None,
        "avgTradedValueCr": round(float((c * v).tail(20).mean()) / 1e7, 1),
        "support": supports, "resistance": resist, "hi52": round(hi52, 1), "lo52": round(lo52, 1),
        "pctFromHi52": round((last / hi52 - 1) * 100, 1), "setup": setup,
    }


def main():
    syms = universe()
    tickers = [s + ".NS" for s in syms]
    print(f"Downloading {len(tickers)} symbols…")
    raw = yf.download(tickers, period="18mo", interval="1d", group_by="ticker", auto_adjust=True,
                      threads=True, progress=False)
    tech, closes = {}, {}
    for s, t in zip(syms, tickers):
        try:
            df = raw[t].dropna(how="all") if len(tickers) > 1 else raw.dropna(how="all")
            a = analyse(df)
            if a:
                tech[s] = a
                closes[s] = {str(k.date()): round(float(x), 2) for k, x in df["Close"].dropna().tail(400).items()}
        except Exception as e:
            print("skip", s, e)

    market = {}
    idx = yf.download(list(INDICES.values()), period="9mo", interval="1d", group_by="ticker",
                      auto_adjust=True, progress=False)
    for name, t in INDICES.items():
        try:
            c = idx[t]["Close"].dropna()
            last = float(c.iloc[-1])
            r = lambda n: round((last / float(c.iloc[-n - 1]) - 1) * 100, 2) if len(c) > n else None
            market[name] = {"value": round(last, 2), "asOf": str(c.index[-1].date()),
                            "chg1d": r(1), "ret1m": r(21), "ret3m": r(63), "ret6m": r(126)}
            if name == "NIFTY 50":
                closes["^NIFTY50"] = {str(k.date()): round(float(x), 2) for k, x in c.tail(400).items()}
        except Exception as e:
            print("index skip", name, e)

    now = dt.datetime.now(IST).isoformat(timespec="minutes")
    json.dump({"generatedAt": now, "count": len(tech), "symbols": tech}, open(os.path.join(DATA, "technicals.json"), "w"), indent=0)
    json.dump({"generatedAt": now, "closes": closes}, open(os.path.join(DATA, "closes.json"), "w"))
    json.dump({"generatedAt": now, "indices": market}, open(os.path.join(DATA, "market.json"), "w"), indent=1)
    print(f"Wrote technicals for {len(tech)} symbols, {len(market)} indices at {now}")


if __name__ == "__main__":
    main()
