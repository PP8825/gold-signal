"""
Daily Portfolio Summary → LINE (Thai)
======================================
Sends a morning summary of the forward-test portfolio to LINE.
Does NOT trade — just reports current status.

Usage:
    python daily_summary.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gold_signal import send_line, build_series, compute_signal, CONFIG

BKK_TZ = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).parent

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("daily_summary")


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


def build_summary() -> str:
    portfolio = load_portfolio()
    if portfolio is None:
        return "⚠️ ยังไม่มีข้อมูลพอร์ต — รอสัญญาณซื้อ/ขายครั้งแรก"

    trades = load_trade_log()
    now = datetime.now(BKK_TZ)

    # Try to get current price
    try:
        df = build_series()
        sig = compute_signal(df)
        current_price = sig.price
        signal_th = {"BUY": "ซื้อ", "SELL": "ขาย", "HOLD": "ถือ"}[sig.action]
    except Exception:
        current_price = portfolio.get("last_price", 0)
        signal_th = "ไม่ทราบ"

    cash = portfolio.get("cash", 0)
    gold = portfolio.get("gold_units", 0)
    initial = portfolio.get("initial_cash", 100000)
    pos_th = {"CASH": "เงินสด", "GOLD": "ถือทอง"}.get(
        portfolio.get("position", "CASH"), "ไม่ทราบ"
    )

    port_value = cash + gold * current_price
    pnl = port_value - initial
    pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

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

    # Count wins
    wins = 0
    for i in range(1, len(trades), 2):  # every SELL after a BUY
        if i < len(trades):
            buy_val = trades[i - 1].get("value", 0)
            sell_val = trades[i].get("value", 0)
            if sell_val > buy_val:
                wins += 1
    pairs = len(trades) // 2

    lines = [
        f"📊 สรุปพอร์ตทองคำประจำวัน",
        f"──────────────",
        f"วันที่: {now.strftime('%Y-%m-%d')} (วันที่ {days_in} ของการทดสอบ)",
        f"ช่วงทดสอบ: {test_start} → {test_end}",
        f"",
        f"💰 มูลค่าพอร์ต: {port_value:,.2f} บาท",
        f"📈 กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)",
        f"",
        f"สถานะ: {pos_th}",
        f"เงินสด: {cash:,.2f} บาท",
        f"ทองคำ: {gold:.4f} บาททอง",
        f"ราคาทอง: {current_price:,.2f} บาท/บาททอง",
        f"",
        f"สัญญาณปัจจุบัน: {signal_th}",
        f"จำนวนรอบซื้อขาย: {len(trades)} ({pairs} คู่)",
    ]

    if pairs > 0:
        lines.append(f"ชนะ/แพ้: {wins}/{pairs - wins}")

    return "\n".join(lines)


def run():
    msg = build_summary()
    print(msg)
    ok = send_line(msg)
    if ok:
        log.info("Daily summary sent to LINE.")
    else:
        log.warning("Failed to send daily summary.")


if __name__ == "__main__":
    run()
