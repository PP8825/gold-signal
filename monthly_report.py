"""
Monthly Report Summary → LINE (Thai)
=====================================
Generates the Excel report and sends a summary to LINE.
Called by GitHub Actions at the end of the 30-day test period.

Usage:
    python monthly_report.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gold_signal import send_line, CONFIG

BKK_TZ = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).parent

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("monthly_report")


def run():
    pf_path = BASE_DIR / "portfolio_state.json"
    tl_path = BASE_DIR / "trade_log.json"

    if not pf_path.exists():
        log.warning("No portfolio state found. Skipping monthly report.")
        return

    with open(pf_path) as f:
        portfolio = json.load(f)

    trades = []
    if tl_path.exists():
        with open(tl_path) as f:
            trades = json.load(f)

    # Generate Excel report
    try:
        from generate_report import generate_report
        report_path = generate_report()
        log.info("Excel report generated: %s", report_path)
    except Exception as e:
        log.error("Failed to generate Excel report: %s", e)

    # Build summary
    initial = portfolio.get("initial_cash", 100000)
    cash = portfolio.get("cash", 0)
    gold = portfolio.get("gold_units", 0)
    last_price = portfolio.get("last_price", 0)
    port_value = cash + gold * last_price
    pnl = port_value - initial
    pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

    test_start = portfolio.get("test_start", "")[:10]
    test_end = portfolio.get("test_end", "")[:10]

    # Trade stats
    total_trades = len(trades)
    pairs = total_trades // 2
    wins = 0
    total_profit = 0
    total_loss = 0
    for i in range(1, total_trades, 2):
        buy_val = trades[i - 1].get("value", 0)
        sell_val = trades[i].get("value", 0)
        diff = sell_val - buy_val
        if diff > 0:
            wins += 1
            total_profit += diff
        else:
            total_loss += abs(diff)

    win_rate = (wins / pairs * 100) if pairs > 0 else 0

    lines = [
        f"📋 สรุปผลการทดสอบพอร์ตทองคำ 1 เดือน",
        f"══════════════════════════",
        f"ช่วงทดสอบ: {test_start} → {test_end}",
        f"",
        f"💰 ผลลัพธ์",
        f"เงินทุนเริ่มต้น: {initial:,.2f} บาท",
        f"มูลค่าสิ้นสุด: {port_value:,.2f} บาท",
        f"กำไร/ขาดทุนสุทธิ: {pnl:+,.2f} บาท ({pnl_pct:+.2f}%)",
        f"",
        f"📊 สถิติการซื้อขาย",
        f"จำนวนรอบซื้อขาย: {total_trades} ครั้ง ({pairs} คู่)",
        f"ชนะ: {wins} / แพ้: {pairs - wins}",
        f"อัตราชนะ: {win_rate:.1f}%",
        f"กำไรรวม: {total_profit:+,.2f} บาท",
        f"ขาดทุนรวม: {total_loss:,.2f} บาท",
        f"",
        f"📁 รายงาน Excel ถูกบันทึกใน GitHub repo แล้ว",
        f"ดาวน์โหลดได้จาก repo → ไฟล์ Gold_Forward_Test_Report.xlsx",
    ]

    msg = "\n".join(lines)
    print(msg)
    ok = send_line(msg)
    if ok:
        log.info("Monthly summary sent to LINE.")
    else:
        log.warning("Failed to send monthly summary.")


if __name__ == "__main__":
    run()
