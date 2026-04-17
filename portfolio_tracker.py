"""
Gold Forward-Test Portfolio Tracker
====================================
Paper-trades Thai gold based on signals from gold_signal.py.
Maintains a portfolio state file and a trade log.

- Starts with a configurable initial cash balance (default 100,000 THB).
- On BUY: spends all cash on gold (baht-weight units).
- On SELL: sells all gold for cash.
- On HOLD: does nothing.
- Records every trade with timestamp, price, action, units, value.

Usage:
    python portfolio_tracker.py              # normal run (trade if signal flips)
    python portfolio_tracker.py --force      # force-push LINE even on HOLD
    python portfolio_tracker.py --report     # generate Excel report
    python portfolio_tracker.py --status     # print current portfolio
"""

from __future__ import annotations

import json
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from gold_signal import (
    build_series, compute_signal, send_line, load_state, save_state, CONFIG
)

BKK_TZ = timezone(timedelta(hours=7))

PORTFOLIO_CONFIG = {
    "INITIAL_CASH": 100_000.0,
    "PORTFOLIO_FILE": str(
        Path(__file__).parent / "portfolio_state.json"
    ),
    "TRADE_LOG": str(
        Path(__file__).parent / "trade_log.json"
    ),
    "TEST_START": "2026-04-18T09:00:00+07:00",  # Start: 18 April 2026, 9AM Bangkok
    "TEST_DURATION_DAYS": 30,
}

log = logging.getLogger("portfolio")


# ---------------------------------------------------------------------------
# PORTFOLIO STATE
# ---------------------------------------------------------------------------
def load_portfolio() -> dict:
    p = Path(PORTFOLIO_CONFIG["PORTFOLIO_FILE"])
    if p.exists():
        with open(p) as f:
            return json.load(f)
    # First run — initialise
    start = PORTFOLIO_CONFIG["TEST_START"]
    start_dt = datetime.fromisoformat(start)
    state = {
        "initial_cash": PORTFOLIO_CONFIG["INITIAL_CASH"],
        "cash": PORTFOLIO_CONFIG["INITIAL_CASH"],
        "gold_units": 0.0,       # baht-weight
        "position": "CASH",      # "CASH" or "GOLD"
        "test_start": start,
        "test_end": (start_dt + timedelta(days=PORTFOLIO_CONFIG["TEST_DURATION_DAYS"])).isoformat(),
        "last_price": 0.0,
        "trades": [],
    }
    save_portfolio(state)
    return state


def save_portfolio(state: dict):
    with open(PORTFOLIO_CONFIG["PORTFOLIO_FILE"], "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_trade_log() -> list:
    p = Path(PORTFOLIO_CONFIG["TRADE_LOG"])
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return []


def save_trade_log(trades: list):
    with open(PORTFOLIO_CONFIG["TRADE_LOG"], "w") as f:
        json.dump(trades, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# TRADING ENGINE
# ---------------------------------------------------------------------------
def execute_trade(portfolio: dict, action: str, price: float) -> Optional[dict]:
    """
    Execute a paper trade. Returns trade record or None if no trade.
    - BUY: convert all cash → gold units
    - SELL: convert all gold → cash
    """
    now = datetime.now(BKK_TZ)

    if action == "BUY" and portfolio["position"] == "CASH" and portfolio["cash"] > 0:
        units = portfolio["cash"] / price
        trade = {
            "timestamp": now.isoformat(),
            "action": "BUY",
            "price": price,
            "units": round(units, 6),
            "value": round(portfolio["cash"], 2),
            "cash_before": round(portfolio["cash"], 2),
            "cash_after": 0.0,
            "gold_before": round(portfolio["gold_units"], 6),
            "gold_after": round(units, 6),
        }
        portfolio["gold_units"] = units
        portfolio["cash"] = 0.0
        portfolio["position"] = "GOLD"
        portfolio["last_price"] = price
        return trade

    elif action == "SELL" and portfolio["position"] == "GOLD" and portfolio["gold_units"] > 0:
        cash_received = portfolio["gold_units"] * price
        trade = {
            "timestamp": now.isoformat(),
            "action": "SELL",
            "price": price,
            "units": round(portfolio["gold_units"], 6),
            "value": round(cash_received, 2),
            "cash_before": 0.0,
            "cash_after": round(cash_received, 2),
            "gold_before": round(portfolio["gold_units"], 6),
            "gold_after": 0.0,
        }
        portfolio["cash"] = cash_received
        portfolio["gold_units"] = 0.0
        portfolio["position"] = "CASH"
        portfolio["last_price"] = price
        return trade

    return None


def portfolio_value(portfolio: dict, current_price: float) -> float:
    return portfolio["cash"] + portfolio["gold_units"] * current_price


def portfolio_summary(portfolio: dict, current_price: float) -> str:
    val = portfolio_value(portfolio, current_price)
    pnl = val - portfolio["initial_cash"]
    pnl_pct = (pnl / portfolio["initial_cash"]) * 100
    trades = load_trade_log()
    pos_th = {"CASH": "เงินสด", "GOLD": "ถือทอง"}.get(portfolio["position"], portfolio["position"])

    return (
        f"สถานะพอร์ต\n"
        f"══════════════════\n"
        f"เริ่มต้น: {portfolio['test_start'][:10]}\n"
        f"สิ้นสุด: {portfolio['test_end'][:10]}\n"
        f"เงินทุนเริ่มต้น: {portfolio['initial_cash']:,.2f} บาท\n\n"
        f"สถานะ: {pos_th}\n"
        f"เงินสด: {portfolio['cash']:,.2f} บาท\n"
        f"ทองคำ: {portfolio['gold_units']:.4f} บาททอง\n"
        f"ราคาล่าสุด: {current_price:,.2f} บาท/บาททอง\n\n"
        f"มูลค่าพอร์ต: {val:,.2f} บาท\n"
        f"กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)\n"
        f"จำนวนรอบซื้อขาย: {len(trades)}\n"
    )


def trade_to_line_text(trade: dict, portfolio: dict, current_price: float) -> str:
    action_th = {"BUY": "ซื้อ", "SELL": "ขาย"}[trade["action"]]
    emoji = {"BUY": "🟢", "SELL": "🔴"}[trade["action"]]
    val = portfolio_value(portfolio, current_price)
    pnl = val - portfolio["initial_cash"]
    pnl_pct = (pnl / portfolio["initial_cash"]) * 100
    trades = load_trade_log()
    pos_th = {"CASH": "เงินสด", "GOLD": "ถือทอง"}.get(portfolio["position"], portfolio["position"])

    lines = [
        f"{emoji} ทำรายการ: {action_th}ทองคำ",
        f"──────────────",
        f"ราคา: {trade['price']:,.2f} บาท/บาททอง",
        f"จำนวน: {trade['units']:.4f} บาททอง",
        f"มูลค่า: {trade['value']:,.2f} บาท",
        f"เวลา: {trade['timestamp'][:16]}",
        f"",
        f"พอร์ตหลังทำรายการ:",
        f"• เงินสด: {portfolio['cash']:,.2f} บาท",
        f"• ทองคำ: {portfolio['gold_units']:.4f} บาททอง",
        f"• มูลค่าพอร์ต: {val:,.2f} บาท",
        f"• กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)",
        f"• จำนวนรอบซื้อขาย: {len(trades)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def run_forward_test(force: bool = False):
    portfolio = load_portfolio()
    trades = load_trade_log()

    now = datetime.now(BKK_TZ)

    # Check if test has started yet
    test_start = datetime.fromisoformat(portfolio["test_start"])
    if test_start.tzinfo is None:
        test_start = test_start.replace(tzinfo=BKK_TZ)
    if now < test_start:
        log.info("Forward test hasn't started yet (starts %s). Waiting...",
                 portfolio["test_start"][:10])
        return

    # Check if test period expired
    test_end = datetime.fromisoformat(portfolio["test_end"])
    if test_end.tzinfo is None:
        test_end = test_end.replace(tzinfo=BKK_TZ)

    if now > test_end:
        log.info("Forward test period ended on %s. Run --report to generate Excel.",
                 portfolio["test_end"][:10])
        print(f"Forward test ended on {portfolio['test_end'][:10]}.")
        print(f"Run: python portfolio_tracker.py --report")
        return

    # Build price series and compute signal
    df = build_series()
    sig = compute_signal(df)
    current_price = sig.price

    log.info("Signal: %s @ %.2f | Position: %s",
             sig.action, current_price, portfolio["position"])

    # Execute trade if signal says BUY/SELL
    trade = None
    if sig.action in ("BUY", "SELL"):
        trade = execute_trade(portfolio, sig.action, current_price)

    # Update last seen price regardless
    portfolio["last_price"] = current_price
    save_portfolio(portfolio)

    if trade:
        trades.append(trade)
        save_trade_log(trades)
        msg = trade_to_line_text(trade, portfolio, current_price)
        print(msg)
        send_line(msg)
    else:
        log.info("No trade (action=%s, position=%s). Portfolio value: %.2f",
                 sig.action, portfolio["position"],
                 portfolio_value(portfolio, current_price))
        if force:
            print(portfolio_summary(portfolio, current_price))


def print_status():
    portfolio = load_portfolio()
    if portfolio["last_price"] > 0:
        print(portfolio_summary(portfolio, portfolio["last_price"]))
    else:
        print("No price data yet. Run the tracker first.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s | %(message)s")

    if "--report" in sys.argv:
        from generate_report import generate_report
        generate_report()
    elif "--status" in sys.argv:
        print_status()
    else:
        force = "--force" in sys.argv
        run_forward_test(force=force)
