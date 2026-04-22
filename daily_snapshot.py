"""
Daily Portfolio Snapshot
========================
Runs once per day. Records portfolio value to daily_history.json
and sends a LINE summary in Thai. Even on days with no trades,
it captures the portfolio value so the cumulative report shows
a complete day-by-day picture.

Usage:
    python daily_snapshot.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gold_signal import send_line, build_series, compute_signal

BKK_TZ = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).parent
HISTORY_FILE = BASE_DIR / "daily_history.json"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("daily_snapshot")


def load_portfolio() -> dict | None:
    p = BASE_DIR / "portfolio_state.json"
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def load_trade_log() -> list:
    p = BASE_DIR / "trade_log.json"
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f)


def load_daily_history() -> list:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []


def save_daily_history(history: list):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, default=str)


def run():
    portfolio = load_portfolio()
    if portfolio is None:
        log.info("No portfolio yet. Skipping snapshot.")
        return

    trades = load_trade_log()
    now = datetime.now(BKK_TZ)
    today = now.strftime("%Y-%m-%d")

    # Get current gold price
    try:
        df = build_series()
        sig = compute_signal(df)
        current_price = sig.price
        signal_th = {"BUY": "ซื้อ", "SELL": "ขาย", "HOLD": "ถือ"}[sig.action]
    except Exception as e:
        log.warning("Failed to get price: %s", e)
        current_price = portfolio.get("last_price", 0)
        signal_th = "ไม่ทราบ"

    cash = portfolio.get("cash", 0)
    gold = portfolio.get("gold_units", 0)
    initial = portfolio.get("initial_cash", 500000)
    port_value = cash + gold * current_price
    pnl = port_value - initial
    pnl_pct = (pnl / initial) * 100 if initial > 0 else 0
    gold_value = gold * current_price
    g_pct = (gold_value / port_value * 100) if port_value > 0 else 0

    # Count today's trades
    today_trades = [t for t in trades if t.get("timestamp", "")[:10] == today]
    buys_today = sum(1 for t in today_trades if t["action"] == "BUY")
    sells_today = sum(1 for t in today_trades if t["action"] == "SELL")

    # Days into test
    test_start = portfolio.get("test_start", "")[:10]
    test_end = portfolio.get("test_end", "")[:10]
    try:
        start_dt = datetime.fromisoformat(portfolio["test_start"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=BKK_TZ)
        days_in = (now - start_dt).days
    except Exception:
        days_in = 0

    # Win/loss stats
    total_trades = len(trades)
    pairs = 0
    wins = 0
    total_profit = 0
    total_loss = 0
    # Match BUY-SELL pairs sequentially
    buy_stack = []
    for t in trades:
        if t["action"] == "BUY":
            buy_stack.append(t)
        elif t["action"] == "SELL" and buy_stack:
            buy_t = buy_stack.pop(0)
            diff = t["value"] - buy_t["value"]
            pairs += 1
            if diff > 0:
                wins += 1
                total_profit += diff
            else:
                total_loss += abs(diff)

    # Save daily snapshot
    history = load_daily_history()
    snapshot = {
        "date": today,
        "price": round(current_price, 2),
        "cash": round(cash, 2),
        "gold_units": round(gold, 6),
        "gold_value": round(gold_value, 2),
        "port_value": round(port_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "total_trades": total_trades,
        "signal": signal_th,
        "buys_today": buys_today,
        "sells_today": sells_today,
    }

    # Replace if same date exists, otherwise append
    history = [h for h in history if h["date"] != today]
    history.append(snapshot)
    history.sort(key=lambda x: x["date"])
    save_daily_history(history)
    log.info("Snapshot saved for %s", today)

    # Build LINE message
    trade_line = ""
    if buys_today > 0 or sells_today > 0:
        parts = []
        if buys_today > 0:
            parts.append(f"ซื้อ {buys_today} ครั้ง")
        if sells_today > 0:
            parts.append(f"ขาย {sells_today} ครั้ง")
        trade_line = f"วันนี้: {', '.join(parts)}\n"
    else:
        trade_line = "วันนี้: ไม่มีรายการซื้อขาย\n"

    lines = [
        f"📊 สรุปพอร์ตทองคำ",
        f"──────────────",
        f"วันที่: {today} (วันที่ {days_in})",
        f"",
        f"💰 มูลค่าพอร์ต: {port_value:,.2f} บาท",
        f"📈 กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)",
        f"",
        f"เงินสด: {cash:,.2f} บาท ({100 - g_pct:.0f}%)",
        f"ทองคำ: {gold:.4f} บาททอง ({g_pct:.0f}%)",
        f"ราคาทอง: {current_price:,.2f} บาท/บาททอง",
        f"สัญญาณ: {signal_th}",
        f"",
        f"{trade_line}",
        f"รวมทั้งหมด: {total_trades} รายการ ({pairs} คู่)",
    ]

    if pairs > 0:
        win_rate = (wins / pairs * 100)
        lines.append(f"ชนะ {wins} / แพ้ {pairs - wins} (อัตราชนะ {win_rate:.0f}%)")
        lines.append(f"กำไรรวม: {total_profit:+,.2f} / ขาดทุนรวม: {total_loss:,.2f}")

    msg = "\n".join(lines)
    print(msg)
    ok = send_line(msg)
    if ok:
        log.info("Daily snapshot sent to LINE.")
    else:
        log.warning("Failed to send daily snapshot to LINE.")


if __name__ == "__main__":
    run()
