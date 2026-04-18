"""
Thai Gold Buy/Sell Signal Alert System
=======================================
Fetches Thai gold spot prices, computes multi-indicator signals
(RSI + MACD + Moving Average crossover), and pushes buy/sell alerts
to LINE via the LINE Messaging API.

Designed to run every hour. A signal is only sent when it changes
from the previous run (no duplicate HOLD spam).

DISCLAIMER
----------
This is a technical-analysis research tool, NOT financial advice.
Gold prices are volatile. Use at your own risk.
"""

from __future__ import annotations

import json
import os
import sys
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# CONFIG — edit these (or load from environment)
# ---------------------------------------------------------------------------
CONFIG = {
    # LINE Messaging API
    # Create a channel at https://developers.line.biz/console/
    # then get the "Channel access token (long-lived)".
    "LINE_CHANNEL_ACCESS_TOKEN": os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
    # Your LINE user ID (click "Your user ID" in the channel's Basic settings)
    # OR a group/room ID. Multiple IDs can be comma-separated.
    "LINE_TO": os.environ.get("LINE_TO", ""),

    # Indicator parameters
    "RSI_PERIOD": 14,
    "RSI_BUY_THRESHOLD": 35,       # buy below this
    "RSI_SELL_THRESHOLD": 65,      # sell above this
    "MA_FAST": 10,
    "MA_SLOW": 30,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,

    # At least this many of the 3 indicators must agree for a BUY/SELL
    "MIN_AGREEMENT": 2,

    # Storage
    "STATE_FILE": str(Path(__file__).parent / ".thai_gold_signal_state.json"),
    "HISTORY_CSV": str(Path(__file__).parent / ".thai_gold_history.csv"),

    # Fetch behaviour
    "FETCH_TIMEOUT": 15,
}

BKK_TZ = timezone(timedelta(hours=7))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
)
log = logging.getLogger("gold_signal")


# ---------------------------------------------------------------------------
# DATA FETCH
# ---------------------------------------------------------------------------
def fetch_thai_gold_spot() -> Optional[float]:
    """
    Fetch current Thai gold bar buy price (THB per baht-weight 96.5%).
    Primary source: Gold Traders Association of Thailand.
    """
    url = "https://www.goldtraders.or.th/UpdatePriceList.aspx"
    try:
        r = requests.get(url, timeout=CONFIG["FETCH_TIMEOUT"],
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = r.text
        # Extract the bar-gold SELL price ("ทองคำแท่ง ขายออก")
        # The page embeds values in input fields with known IDs.
        import re
        m = re.search(
            r'id="DetailPlace_uc_goldprices1_lblBLSell"[^>]*>([\d,]+\.\d+)',
            text,
        )
        if m:
            return float(m.group(1).replace(",", ""))
    except Exception as e:
        log.warning("goldtraders.or.th failed: %s", e)
    return None


def fetch_xau_usd_history(period: str = "60d",
                          interval: str = "1h") -> pd.DataFrame:
    """
    Fallback history source: XAU/USD (gold spot in USD) via yfinance.
    Converted to approx THB/baht-weight so indicator math is consistent.

    baht-weight (15.244 g of 96.5% gold) ≈ 15.244 * 0.965 g of pure gold
                                           = 14.71046 g
    1 troy oz = 31.1035 g
    So 1 baht-weight pure ≈ 14.71046 / 31.1035 ≈ 0.4729 oz
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError(
            "yfinance is not installed. Run: pip install yfinance"
        )

    gold = yf.Ticker("GC=F").history(period=period, interval=interval)
    if gold.empty:
        raise RuntimeError("No gold data from yfinance")

    fx = yf.Ticker("THB=X").history(period=period, interval=interval)
    if fx.empty:
        # USDTHB not available at that interval; use daily and forward-fill
        fx = yf.Ticker("THB=X").history(period=period, interval="1d")

    df = gold[["Close"]].rename(columns={"Close": "xau_usd"})
    fx = fx[["Close"]].rename(columns={"Close": "usdthb"})
    df = df.join(fx, how="left").ffill().dropna()

    oz_per_baht_weight = 14.71046 / 31.1035
    df["price"] = df["xau_usd"] * df["usdthb"] * oz_per_baht_weight
    return df[["price"]]


def load_history_csv() -> pd.DataFrame:
    p = Path(CONFIG["HISTORY_CSV"])
    if p.exists():
        df = pd.read_csv(p, parse_dates=["ts"])
        df = df.set_index("ts")
        return df
    return pd.DataFrame(columns=["price"]).set_index(
        pd.DatetimeIndex([], name="ts")
    )


def append_history(price: float) -> pd.DataFrame:
    """Append latest spot to persisted CSV and return full series."""
    df = load_history_csv()
    now = pd.Timestamp(datetime.now(BKK_TZ)).tz_convert("Asia/Bangkok")
    df.loc[now] = {"price": price}
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(CONFIG["HISTORY_CSV"], index_label="ts")
    return df


def build_series() -> pd.DataFrame:
    """
    Build a price history long enough for indicators.
    Strategy:
      1. Try Thai spot (goldtraders.or.th) — append to persisted CSV.
      2. If that file is too short, hydrate with converted XAU/USD history.
    """
    spot = fetch_thai_gold_spot()
    hist = load_history_csv()

    if spot is not None:
        hist = append_history(spot)
        log.info("Fetched Thai spot: %.2f THB/baht-weight", spot)

    if len(hist) >= max(CONFIG["MA_SLOW"], CONFIG["MACD_SLOW"]) + 5:
        return hist

    # Hydrate with yfinance XAU/USD
    log.info("Hydrating history from yfinance XAU/USD…")
    yhist = fetch_xau_usd_history()
    yhist.index = yhist.index.tz_convert("Asia/Bangkok") \
        if yhist.index.tz is not None else \
        yhist.index.tz_localize("UTC").tz_convert("Asia/Bangkok")
    combined = pd.concat([yhist, hist])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined


# ---------------------------------------------------------------------------
# INDICATORS (pure numpy / pandas — no TA-Lib needed)
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist_ = macd_line - signal_line
    return macd_line, signal_line, hist_


def moving_averages(series: pd.Series, fast: int, slow: int):
    return series.rolling(fast).mean(), series.rolling(slow).mean()


# ---------------------------------------------------------------------------
# SIGNAL ENGINE
# ---------------------------------------------------------------------------
@dataclass
class Signal:
    action: str             # "BUY", "SELL", or "HOLD"
    price: float
    ts: datetime
    rsi: float
    macd_hist: float
    ma_fast: float
    ma_slow: float
    votes: dict             # per-indicator vote
    reasons: list

    def to_line_text(self) -> str:
        action_th = {"BUY": "ซื้อ", "SELL": "ขาย", "HOLD": "ถือ"}[self.action]
        emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}[self.action]
        vote_th = {"BUY": "ซื้อ", "SELL": "ขาย", "HOLD": "ถือ"}

        reason_map = {
            "oversold": "oversold (ขายมากเกินไป)",
            "overbought": "overbought (ซื้อมากเกินไป)",
            "MACD bullish cross": "MACD ตัดขึ้น (สัญญาณซื้อ)",
            "MACD bearish cross": "MACD ตัดลง (สัญญาณขาย)",
            "MA golden cross": "MA ตัดขึ้น (Golden Cross)",
            "MA death cross": "MA ตัดลง (Death Cross)",
        }
        reasons_th = []
        for r in self.reasons:
            matched = False
            for eng, th in reason_map.items():
                if eng in r:
                    reasons_th.append(r.replace(eng, th))
                    matched = True
                    break
            if not matched:
                reasons_th.append(r)

        return (
            f"{emoji} สัญญาณทองคำ: {action_th}\n"
            f"──────────────\n"
            f"ทองคำแท่ง 96.5%: {self.price:,.2f} บาท/บาททอง\n"
            f"เวลา: {self.ts.strftime('%Y-%m-%d %H:%M')} (กรุงเทพฯ)\n\n"
            f"ตัวชี้วัด\n"
            f"• RSI({CONFIG['RSI_PERIOD']}): {self.rsi:.1f} "
            f"→ {vote_th[self.votes['rsi']]}\n"
            f"• MACD hist: {self.macd_hist:+.2f} "
            f"→ {vote_th[self.votes['macd']]}\n"
            f"• MA{CONFIG['MA_FAST']}/MA{CONFIG['MA_SLOW']}: "
            f"{self.ma_fast:,.0f} / {self.ma_slow:,.0f} "
            f"→ {vote_th[self.votes['ma']]}\n\n"
            f"เหตุผล: {'; '.join(reasons_th) if reasons_th else 'ไม่มีสัญญาณชัดเจน'}"
        )


def compute_signal(df: pd.DataFrame) -> Signal:
    p = df["price"].astype(float)

    r = rsi(p, CONFIG["RSI_PERIOD"])
    macd_line, macd_sig, macd_hist = macd(
        p, CONFIG["MACD_FAST"], CONFIG["MACD_SLOW"], CONFIG["MACD_SIGNAL"]
    )
    ma_f, ma_s = moving_averages(p, CONFIG["MA_FAST"], CONFIG["MA_SLOW"])

    last = {
        "price": float(p.iloc[-1]),
        "rsi": float(r.iloc[-1]),
        "macd_hist": float(macd_hist.iloc[-1]),
        "macd_hist_prev": float(macd_hist.iloc[-2]) if len(macd_hist) > 1 else 0.0,
        "ma_fast": float(ma_f.iloc[-1]),
        "ma_slow": float(ma_s.iloc[-1]),
        "ma_fast_prev": float(ma_f.iloc[-2]) if len(ma_f) > 1 else 0.0,
        "ma_slow_prev": float(ma_s.iloc[-2]) if len(ma_s) > 1 else 0.0,
    }

    votes, reasons = {}, []

    # RSI vote
    if last["rsi"] < CONFIG["RSI_BUY_THRESHOLD"]:
        votes["rsi"] = "BUY"
        reasons.append(f"RSI {last['rsi']:.1f} oversold")
    elif last["rsi"] > CONFIG["RSI_SELL_THRESHOLD"]:
        votes["rsi"] = "SELL"
        reasons.append(f"RSI {last['rsi']:.1f} overbought")
    else:
        votes["rsi"] = "HOLD"

    # MACD vote (cross of histogram through zero)
    if last["macd_hist"] > 0 and last["macd_hist_prev"] <= 0:
        votes["macd"] = "BUY"
        reasons.append("MACD bullish cross")
    elif last["macd_hist"] < 0 and last["macd_hist_prev"] >= 0:
        votes["macd"] = "SELL"
        reasons.append("MACD bearish cross")
    elif last["macd_hist"] > 0:
        votes["macd"] = "BUY"
    elif last["macd_hist"] < 0:
        votes["macd"] = "SELL"
    else:
        votes["macd"] = "HOLD"

    # MA cross vote
    golden_cross = (last["ma_fast"] > last["ma_slow"] and
                    last["ma_fast_prev"] <= last["ma_slow_prev"])
    death_cross = (last["ma_fast"] < last["ma_slow"] and
                   last["ma_fast_prev"] >= last["ma_slow_prev"])
    if golden_cross:
        votes["ma"] = "BUY"; reasons.append("MA golden cross")
    elif death_cross:
        votes["ma"] = "SELL"; reasons.append("MA death cross")
    elif last["ma_fast"] > last["ma_slow"]:
        votes["ma"] = "BUY"
    elif last["ma_fast"] < last["ma_slow"]:
        votes["ma"] = "SELL"
    else:
        votes["ma"] = "HOLD"

    buys = sum(1 for v in votes.values() if v == "BUY")
    sells = sum(1 for v in votes.values() if v == "SELL")

    if buys >= CONFIG["MIN_AGREEMENT"] and buys > sells:
        action = "BUY"
    elif sells >= CONFIG["MIN_AGREEMENT"] and sells > buys:
        action = "SELL"
    else:
        action = "HOLD"

    return Signal(
        action=action,
        price=last["price"],
        ts=datetime.now(BKK_TZ),
        rsi=last["rsi"],
        macd_hist=last["macd_hist"],
        ma_fast=last["ma_fast"],
        ma_slow=last["ma_slow"],
        votes=votes,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# LINE MESSAGING API
# ---------------------------------------------------------------------------
def send_line(text: str) -> bool:
    token = CONFIG["LINE_CHANNEL_ACCESS_TOKEN"]
    to = CONFIG["LINE_TO"]
    if not token or not to:
        log.warning("LINE credentials missing — skipping push. "
                    "Set LINE_CHANNEL_ACCESS_TOKEN and LINE_TO.")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    ok = True
    for recipient in [x.strip() for x in to.split(",") if x.strip()]:
        payload = {
            "to": recipient,
            "messages": [{"type": "text", "text": text[:4900]}],
        }
        try:
            r = requests.post(url, headers=headers, json=payload,
                              timeout=CONFIG["FETCH_TIMEOUT"])
            if r.status_code != 200:
                log.error("LINE push failed (%s): %s", r.status_code, r.text)
                ok = False
            else:
                log.info("LINE push delivered to %s", recipient)
        except Exception as e:
            log.error("LINE push error: %s", e)
            ok = False
    return ok


# ---------------------------------------------------------------------------
# STATE (so we don't spam identical signals)
# ---------------------------------------------------------------------------
def load_state() -> dict:
    try:
        with open(CONFIG["STATE_FILE"]) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    try:
        with open(CONFIG["STATE_FILE"], "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        log.warning("Failed to save state: %s", e)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run_once(force: bool = False) -> Signal:
    df = build_series()
    if len(df) < max(CONFIG["MA_SLOW"], CONFIG["MACD_SLOW"]) + 2:
        raise RuntimeError(
            f"Not enough history ({len(df)} points). Need "
            f"{max(CONFIG['MA_SLOW'], CONFIG['MACD_SLOW']) + 2}."
        )

    sig = compute_signal(df)
    log.info("Signal: %s @ %.2f", sig.action, sig.price)
    log.info("Votes: %s", sig.votes)

    state = load_state()
    last_action = state.get("last_action")

    # Send when BUY/SELL, and either it's new OR user forced it.
    send = force or (sig.action in ("BUY", "SELL") and sig.action != last_action)

    if send:
        ok = send_line(sig.to_line_text())
        if ok:
            state["last_action"] = sig.action
            state["last_sent_ts"] = sig.ts.isoformat()
            save_state(state)
    else:
        log.info("Skipping LINE push (no action change).")
        # Still remember current action for the next comparison
        state["last_seen_action"] = sig.action
        save_state(state)

    return sig


if __name__ == "__main__":
    force_send = "--force" in sys.argv
    try:
        s = run_once(force=force_send)
        print(s.to_line_text())
    except Exception as e:
        log.exception("Run failed: %s", e)
        sys.exit(1)
