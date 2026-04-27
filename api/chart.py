from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import yfinance as yf
import pandas as pd
import numpy as np


def to_ts(dt):
    if pd.isna(dt):
        return None
    if hasattr(dt, "timestamp"):
        return int(dt.timestamp())
    return int(pd.Timestamp(dt).timestamp())


def series_to_list(index, series, decimals=4):
    return [
        {"time": to_ts(dt), "value": round(float(v), decimals)}
        for dt, v in zip(index, series)
        if not pd.isna(v)
    ]


def calc_ichimoku(df):
    h, l, c = df["High"], df["Low"], df["Close"]
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    chikou = c.shift(-26)
    return tenkan, kijun, senkou_a, senkou_b, chikou


def calc_bollinger(close, period=20, std_dev=2):
    ma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return ma, ma + std_dev * std, ma - std_dev * std


def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - (100 / (1 + gain / loss))


def calc_macd(close, fast=12, slow=26, signal=9):
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd = ema_f - ema_s
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig, macd - sig


def calc_stochastic(df, k=14, d=3):
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    stoch_k = 100 * (df["Close"] - low_min) / (high_max - low_min)
    stoch_d = stoch_k.rolling(d).mean()
    return stoch_k, stoch_d


def calc_obv(df):
    closes = df["Close"].values
    volumes = df["Volume"].values
    obv = [0]
    for i in range(1, len(df)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return pd.Series(obv, index=df.index, dtype=float)


def process(params):
    def p(key, default=""):
        return params.get(key, [default])[0]

    ticker = p("ticker", "AAPL").upper()
    period = p("period", "1y")
    interval = p("interval", "1d")
    start = p("start", "")
    end = p("end", "")

    tkr = yf.Ticker(ticker)
    if start and end:
        df = tkr.history(start=start, end=end, interval=interval, auto_adjust=True)
    else:
        df = tkr.history(period=period, interval=interval, auto_adjust=True)

    if df.empty:
        return {"error": f"데이터 없음: {ticker}"}, 404

    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)

    close = df["Close"]

    candles = [
        {
            "time": to_ts(dt),
            "open": round(float(r["Open"]), 4),
            "high": round(float(r["High"]), 4),
            "low": round(float(r["Low"]), 4),
            "close": round(float(r["Close"]), 4),
            "volume": int(r["Volume"]) if not pd.isna(r["Volume"]) else 0,
        }
        for dt, r in df.iterrows()
    ]

    mas = {str(n): series_to_list(df.index, close.rolling(n).mean()) for n in [5, 20, 60, 120, 200]}

    bb_ma, bb_up, bb_lo = calc_bollinger(close)
    bollinger = {
        "mid": series_to_list(df.index, bb_ma),
        "upper": series_to_list(df.index, bb_up),
        "lower": series_to_list(df.index, bb_lo),
    }

    t, k, sa, sb, ch = calc_ichimoku(df)
    ichimoku = {
        "tenkan": series_to_list(df.index, t),
        "kijun": series_to_list(df.index, k),
        "senkou_a": series_to_list(df.index, sa),
        "senkou_b": series_to_list(df.index, sb),
        "chikou": series_to_list(df.index, ch),
    }

    rsi = series_to_list(df.index, calc_rsi(close), 2)

    ml, sl, hist = calc_macd(close)
    macd = {
        "macd": series_to_list(df.index, ml),
        "signal": series_to_list(df.index, sl),
        "histogram": series_to_list(df.index, hist),
    }

    sk, sd = calc_stochastic(df)
    stochastic = {
        "k": series_to_list(df.index, sk, 2),
        "d": series_to_list(df.index, sd, 2),
    }

    obv = series_to_list(df.index, calc_obv(df), 0)

    try:
        name = tkr.info.get("longName", ticker) or ticker
    except Exception:
        name = ticker

    return {
        "ticker": ticker,
        "name": name,
        "candles": candles,
        "mas": mas,
        "bollinger": bollinger,
        "ichimoku": ichimoku,
        "rsi": rsi,
        "macd": macd,
        "stochastic": stochastic,
        "obv": obv,
    }, 200


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            result, status = process(params)
        except Exception as e:
            result, status = {"error": str(e)}, 500

        body = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
