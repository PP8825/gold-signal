"""
Gold Forward-Test Portfolio Tracker (Realistic Simulation)
===========================================================
Paper-trades Thai gold based on signals from gold_signal.py.

Rules:
  - Total capital: 500,000 THB
  - BUY: spend up to 100,000 THB per trade (can buy multiple times)
  - SELL: sell up to 100,000 THB worth of gold per trade
  - No daily trade limit, but respects cash/gold availability
  - Can hold both cash and gold simultaneously (partial positions)

Usage:
    python portfolio_tracker.py              # normal run
    python portfolio_tracker.py --force      # show status even on HOLD
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
    "INITIAL_CASH": 500_000.0,
    "TRADE_SIZE_UNITS": 1.0,          # buy/sell 1 baht-weight of gold per trade
    "PORTFOLIO_FILE": str(
        Path(__file__).parent / "portfolio_state.json"
    ),
    "TRADE_LOG": str(
        Path(__file__).parent / "trade_log.json"
    ),
    "TEST_START": "2026-04-18T09:00:00+07:00",
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
        "gold_units": 0.0,
        "last_price": 0.0,
        "test_start": start,
        "test_end": (start_dt + timedelta(
            days=PORTFOLIO_CONFIG["TEST_DURATION_DAYS"]
        )).isoformat(),
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
# TRADING ENGINE (realistic)
# ---------------------------------------------------------------------------
def execute_trade(portfolio: dict, action: str, price: float) -> Optional[dict]:
    """
    Execute a paper trade with realistic position sizing.
    - BUY: buy 1 baht-weight of gold (if enough cash)
    - SELL: sell 1 baht-weight of gold (if enough gold)
    Returns trade record or None if no trade possible.
    """
    now = datetime.now(BKK_TZ)
    trade_units = PORTFOLIO_CONFIG["TRADE_SIZE_UNITS"]  # 1 baht-weight

    if action == "BUY":
        cost = trade_units * price
        available = portfolio["cash"]
        if available < price * 0.1:  # can't even buy 0.1 baht-weight
            log.info("BUY signal but not enough cash (%.2f THB). Skipping.", available)
            return None

        # Buy 1 baht-weight, or whatever cash allows if less than 1
        units_bought = min(trade_units, available / price)
        spend = units_bought * price

        trade = {
            "timestamp": now.isoformat(),
            "action": "BUY",
            "price": round(price, 2),
            "units": round(units_bought, 6),
            "value": round(spend, 2),
            "cash_before": round(portfolio["cash"], 2),
            "cash_after": round(portfolio["cash"] - spend, 2),
            "gold_before": round(portfolio["gold_units"], 6),
            "gold_after": round(portfolio["gold_units"] + units_bought, 6),
        }
        portfolio["cash"] -= spend
        portfolio["gold_units"] += units_bought
        portfolio["last_price"] = price
        return trade

    elif action == "SELL":
        if portfolio["gold_units"] < 0.01:  # basically no gold
            log.info("SELL signal but no gold to sell (%.6f). Skipping.",
                     portfolio["gold_units"])
            return None

        # Sell 1 baht-weight, or whatever is left if less than 1
        units_sold = min(trade_units, portfolio["gold_units"])
        cash_received = units_sold * price

        trade = {
            "timestamp": now.isoformat(),
            "action": "SELL",
            "price": round(price, 2),
            "units": round(units_sold, 6),
            "value": round(cash_received, 2),
            "cash_before": round(portfolio["cash"], 2),
            "cash_after": round(portfolio["cash"] + cash_received, 2),
            "gold_before": round(portfolio["gold_units"], 6),
            "gold_after": round(portfolio["gold_units"] - units_sold, 6),
        }
        portfolio["cash"] += cash_received
        portfolio["gold_units"] -= units_sold
        portfolio["last_price"] = price
        return trade

    return None


def portfolio_value(portfolio: dict, current_price: float) -> float:
    return portfolio["cash"] + portfolio["gold_units"] * current_price


def gold_pct(portfolio: dict, current_price: float) -> float:
    val = portfolio_value(portfolio, current_price)
    if val <= 0:
        return 0.0
    return (portfolio["gold_units"] * current_price / val) * 100


def portfolio_summary(portfolio: dict, current_price: float) -> str:
    val = portfolio_value(portfolio, current_price)
    pnl = val - portfolio["initial_cash"]
    pnl_pct = (pnl / portfolio["initial_cash"]) * 100
    trades = load_trade_log()
    g_pct = gold_pct(portfolio, current_price)
    c_pct = 100 - g_pct

    return (
        f"สถานะพอร์ต\n"
        f"══════════════════\n"
        f"เริ่มต้น: {portfolio['test_start'][:10]}\n"
        f"สิ้นสุด: {portfolio['test_end'][:10]}\n"
        f"เงินทุนเริ่มต้น: {portfolio['initial_cash']:,.2f} บาท\n\n"
        f"เงินสด: {portfolio['cash']:,.2f} บาท ({c_pct:.0f}%)\n"
        f"ทองคำ: {portfolio['gold_units']:.4f} บาททอง ({g_pct:.0f}%)\n"
        f"ราคาทอง: {current_price:,.2f} บาท/บาททอง\n\n"
        f"มูลค่าพอร์ต: {val:,.2f} บาท\n"
        f"กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)\n"
        f"จำนวนรายการ: {len(trades)}\n"
    )


def trade_to_line_text(trade: dict, portfolio: dict, current_price: float) -> str:
    action_th = {"BUY": "ซื้อ", "SELL": "ขาย"}[trade["action"]]
    emoji = {"BUY": "🟢", "SELL": "🔴"}[trade["action"]]
    val = portfolio_value(portfolio, current_price)
    pnl = val - portfolio["initial_cash"]
    pnl_pct = (pnl / portfolio["initial_cash"]) * 100
    trades = load_trade_log()
    g_pct = gold_pct(portfolio, current_price)
    c_pct = 100 - g_pct

    lines = [
        f"{emoji} ทำรายการ: {action_th}ทองคำ",
        f"──────────────",
        f"ราคา: {trade['price']:,.2f} บาท/บาททอง",
        f"จำนวน: {trade['units']:.4f} บาททอง",
        f"มูลค่า: {trade['value']:,.2f} บาท",
        f"เวลา: {trade['timestamp'][:16]}",
        f"",
        f"พอร์ตหลังทำรายการ:",
        f"• เงินสด: {portfolio['cash']:,.2f} บาท ({c_pct:.0f}%)",
        f"• ทองคำ: {portfolio['gold_units']:.4f} บาททอง ({g_pct:.0f}%)",
        f"• มูลค่าพอร์ต: {val:,.2f} บาท",
        f"• กำไร/ขาดทุน: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)",
        f"• จำนวนรายการ: {len(trades)}",
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
        log.info("Forward test ended on %s. Run --report to generate Excel.",
                 portfolio["test_end"][:10])
        print(f"Forward test ended on {portfolio['test_end'][:10]}.")
        print(f"Run: python portfolio_tracker.py --report")
        return

    # Build price series and compute signal
    df = build_series()
    sig = compute_signal(df)
    current_price = sig.price

    log.info("Signal: %s @ %.2f | Cash: %.2f | Gold: %.4f",
             sig.action, current_price, portfolio["cash"],
             portfolio["gold_units"])

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
        log.info("No trade (action=%s). Portfolio value: %.2f",
                 sig.action, portfolio_value(portfolio, current_price))
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
