"""
Generate an interactive HTML dashboard for the gold portfolio.
Embeds all data from JSON files into a single index.html.
Designed to be served via GitHub Pages.

Usage:
    python generate_dashboard.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BKK_TZ = timezone(timedelta(hours=7))
BASE_DIR = Path(__file__).parent


def load_json(filename: str, default=None):
    p = BASE_DIR / filename
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default if default is not None else {}


def generate_dashboard():
    portfolio = load_json("portfolio_state.json", {})
    trades = load_json("trade_log.json", [])
    daily_history = load_json("daily_history.json", [])

    now = datetime.now(BKK_TZ)
    initial = portfolio.get("initial_cash", 500000)
    cash = portfolio.get("cash", 0)
    gold = portfolio.get("gold_units", 0)
    price = portfolio.get("last_price", 0)
    avg_cost = portfolio.get("avg_cost", 0)
    port_value = cash + gold * price
    pnl = port_value - initial
    pnl_pct = (pnl / initial * 100) if initial > 0 else 0

    test_start = portfolio.get("test_start", "")[:10]
    test_end = portfolio.get("test_end", "")[:10]

    # Win/loss
    buy_stack = []
    pairs = wins = 0
    total_profit = total_loss = 0
    for t in trades:
        if t["action"] == "BUY":
            buy_stack.append(t)
        elif t["action"] == "SELL" and buy_stack:
            bt = buy_stack.pop(0)
            diff = t["value"] - bt["value"]
            pairs += 1
            if diff > 0:
                wins += 1
                total_profit += diff
            else:
                total_loss += abs(diff)

    win_rate = (wins / pairs * 100) if pairs > 0 else 0

    # Serialize data for JS
    trades_json = json.dumps(trades, default=str)
    daily_json = json.dumps(daily_history, default=str)

    pnl_color = "#22c55e" if pnl >= 0 else "#ef4444"
    pnl_sign = "+" if pnl >= 0 else ""

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gold Portfolio Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #334155;
    padding: 20px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .header h1 {{
    font-size: 1.5rem;
    color: #fbbf24;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .header .period {{
    color: #94a3b8;
    font-size: 0.85rem;
  }}
  .updated {{
    color: #64748b;
    font-size: 0.8rem;
  }}
  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
  }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }}
  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px;
  }}
  .card .label {{
    color: #94a3b8;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
  }}
  .card .value {{
    font-size: 1.5rem;
    font-weight: 700;
  }}
  .card .sub {{
    color: #64748b;
    font-size: 0.8rem;
    margin-top: 4px;
  }}
  .green {{ color: #22c55e; }}
  .red {{ color: #ef4444; }}
  .gold {{ color: #fbbf24; }}
  .chart-container {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .chart-container h2 {{
    font-size: 1rem;
    color: #cbd5e1;
    margin-bottom: 16px;
  }}
  .chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 24px;
  }}
  @media (max-width: 768px) {{
    .chart-row {{ grid-template-columns: 1fr; }}
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  th {{
    background: #334155;
    color: #cbd5e1;
    padding: 10px 12px;
    text-align: center;
    font-weight: 600;
    position: sticky;
    top: 0;
  }}
  td {{
    padding: 8px 12px;
    text-align: center;
    border-bottom: 1px solid #1e293b;
  }}
  tr:nth-child(even) {{ background: #1e293b; }}
  tr:nth-child(odd) {{ background: #0f172a; }}
  .buy-row {{ background: rgba(34, 197, 94, 0.08) !important; }}
  .sell-row {{ background: rgba(239, 68, 68, 0.08) !important; }}
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.75rem;
  }}
  .badge-buy {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
  .badge-sell {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
  .table-scroll {{
    max-height: 400px;
    overflow-y: auto;
    border-radius: 8px;
    border: 1px solid #334155;
  }}
  .tabs {{
    display: flex;
    gap: 4px;
    margin-bottom: 16px;
  }}
  .tab {{
    padding: 8px 20px;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px 8px 0 0;
    color: #94a3b8;
    cursor: pointer;
    font-size: 0.85rem;
    transition: all 0.2s;
  }}
  .tab.active {{
    background: #334155;
    color: #fbbf24;
    border-bottom-color: #334155;
  }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .stat-row {{
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #1e293b;
  }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{ color: #94a3b8; }}
  .stat-value {{ font-weight: 600; }}
  .allocation-bar {{
    display: flex;
    height: 28px;
    border-radius: 8px;
    overflow: hidden;
    margin-top: 8px;
  }}
  .alloc-cash {{
    background: #3b82f6;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 600;
    transition: width 0.5s;
  }}
  .alloc-gold {{
    background: #fbbf24;
    color: #0f172a;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    font-weight: 600;
    transition: width 0.5s;
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>📊 Gold Portfolio Dashboard</h1>
    <div class="period">Forward Test: {test_start} → {test_end}</div>
  </div>
  <div class="updated">อัปเดตล่าสุด: {now.strftime("%Y-%m-%d %H:%M")} ICT</div>
</div>

<div class="container">

  <!-- Summary Cards -->
  <div class="cards">
    <div class="card">
      <div class="label">มูลค่าพอร์ต</div>
      <div class="value gold">{port_value:,.2f}</div>
      <div class="sub">เริ่มต้น {initial:,.0f} บาท</div>
    </div>
    <div class="card">
      <div class="label">กำไร/ขาดทุน</div>
      <div class="value" style="color:{pnl_color}">{pnl_sign}{pnl:,.2f}</div>
      <div class="sub" style="color:{pnl_color}">{pnl_sign}{pnl_pct:.2f}%</div>
    </div>
    <div class="card">
      <div class="label">ราคาทองปัจจุบัน</div>
      <div class="value">{price:,.2f}</div>
      <div class="sub">บาท/บาททอง</div>
    </div>
    <div class="card">
      <div class="label">ต้นทุนเฉลี่ย</div>
      <div class="value">{avg_cost:,.2f}</div>
      <div class="sub">{"ไม่มีทองคำ" if gold < 0.01 else f"ถือ {gold:.4f} บาททอง"}</div>
    </div>
  </div>

  <!-- Allocation -->
  <div class="card" style="margin-bottom:24px">
    <div class="label">สัดส่วนพอร์ต</div>
    <div style="display:flex;justify-content:space-between;margin-top:8px">
      <span>เงินสด: {cash:,.2f} บาท</span>
      <span class="gold">ทองคำ: {gold * price:,.2f} บาท</span>
    </div>
    <div class="allocation-bar">
      <div class="alloc-cash" style="width:{cash/port_value*100 if port_value > 0 else 100:.0f}%">
        เงินสด {cash/port_value*100 if port_value > 0 else 100:.0f}%
      </div>
      <div class="alloc-gold" style="width:{gold*price/port_value*100 if port_value > 0 else 0:.0f}%">
        {"ทองคำ " + f"{gold*price/port_value*100:.0f}%" if gold > 0.01 else ""}
      </div>
    </div>
  </div>

  <!-- Stats -->
  <div class="cards" style="grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))">
    <div class="card">
      <div class="label">สถิติการเทรด</div>
      <div class="stat-row"><span class="stat-label">รายการทั้งหมด</span><span class="stat-value">{len(trades)}</span></div>
      <div class="stat-row"><span class="stat-label">คู่ BUY-SELL</span><span class="stat-value">{pairs}</span></div>
      <div class="stat-row"><span class="stat-label">ชนะ / แพ้</span><span class="stat-value"><span class="green">{wins}</span> / <span class="red">{pairs - wins}</span></span></div>
      <div class="stat-row"><span class="stat-label">อัตราชนะ</span><span class="stat-value">{win_rate:.0f}%</span></div>
    </div>
    <div class="card">
      <div class="label">กำไร/ขาดทุนจากการเทรด</div>
      <div class="stat-row"><span class="stat-label">กำไรรวม</span><span class="stat-value green">+{total_profit:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">ขาดทุนรวม</span><span class="stat-value red">-{total_loss:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">สุทธิ</span><span class="stat-value" style="color:{pnl_color}">{pnl_sign}{total_profit - total_loss:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">กฎ</span><span class="stat-value" style="font-size:0.75rem;color:#94a3b8">ไม่ขายต่ำกว่าต้นทุน</span></div>
    </div>
  </div>

  <!-- Charts -->
  <div class="chart-row">
    <div class="chart-container">
      <h2>📈 มูลค่าพอร์ตรายวัน</h2>
      <canvas id="valueChart"></canvas>
    </div>
    <div class="chart-container">
      <h2>📊 ผลตอบแทนสะสม (%)</h2>
      <canvas id="returnChart"></canvas>
    </div>
  </div>

  <div class="chart-container">
    <h2>🪙 ราคาทองคำ</h2>
    <canvas id="priceChart"></canvas>
  </div>

  <!-- Tables -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('trades')">รายการซื้อขาย ({len(trades)})</div>
    <div class="tab" onclick="switchTab('daily')">ผลรายวัน ({len(daily_history)})</div>
  </div>

  <div id="trades-tab" class="tab-content active">
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>#</th><th>วัน/เวลา</th><th>รายการ</th><th>ราคา</th>
            <th>จำนวน</th><th>มูลค่า</th><th>เงินสดหลัง</th><th>ทองหลัง</th>
          </tr>
        </thead>
        <tbody id="trade-body"></tbody>
      </table>
    </div>
  </div>

  <div id="daily-tab" class="tab-content">
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>วัน</th><th>วันที่</th><th>ราคาทอง</th><th>เงินสด</th>
            <th>ทองคำ</th><th>มูลค่าพอร์ต</th><th>กำไร/ขาดทุน</th><th>%</th>
            <th>ซื้อ</th><th>ขาย</th>
          </tr>
        </thead>
        <tbody id="daily-body"></tbody>
      </table>
    </div>
  </div>

</div>

<script>
const trades = {trades_json};
const daily = {daily_json};

const fmt = (n) => n.toLocaleString('en-US', {{minimumFractionDigits:2, maximumFractionDigits:2}});

// Trade table
const tbody = document.getElementById('trade-body');
trades.forEach((t, i) => {{
  const cls = t.action === 'BUY' ? 'buy-row' : 'sell-row';
  const badge = t.action === 'BUY'
    ? '<span class="badge badge-buy">ซื้อ</span>'
    : '<span class="badge badge-sell">ขาย</span>';
  tbody.innerHTML += `<tr class="${{cls}}">
    <td>${{i+1}}</td>
    <td>${{t.timestamp.slice(0,16).replace('T',' ')}}</td>
    <td>${{badge}}</td>
    <td>${{fmt(t.price)}}</td>
    <td>${{t.units.toFixed(4)}}</td>
    <td>${{fmt(t.value)}}</td>
    <td>${{fmt(t.cash_after)}}</td>
    <td>${{t.gold_after.toFixed(4)}}</td>
  </tr>`;
}});

// Daily table
const dbody = document.getElementById('daily-body');
daily.forEach((d, i) => {{
  const pcolor = d.pnl >= 0 ? '#22c55e' : '#ef4444';
  dbody.innerHTML += `<tr>
    <td>${{i+1}}</td>
    <td>${{d.date}}</td>
    <td>${{fmt(d.price)}}</td>
    <td>${{fmt(d.cash)}}</td>
    <td>${{d.gold_units.toFixed(4)}}</td>
    <td>${{fmt(d.port_value)}}</td>
    <td style="color:${{pcolor}}">${{d.pnl >= 0 ? '+' : ''}}${{fmt(d.pnl)}}</td>
    <td style="color:${{pcolor}}">${{d.pnl_pct >= 0 ? '+' : ''}}${{d.pnl_pct.toFixed(2)}}%</td>
    <td>${{d.buys_today || '-'}}</td>
    <td>${{d.sells_today || '-'}}</td>
  </tr>`;
}});

// Tab switching
function switchTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById(name + '-tab').classList.add('active');
  event.target.classList.add('active');
}}

// Charts
const chartDefaults = {{
  color: '#94a3b8',
  borderColor: '#334155',
}};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';

if (daily.length >= 1) {{
  const labels = daily.map(d => d.date.slice(5));

  new Chart(document.getElementById('valueChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: 'มูลค่าพอร์ต (บาท)',
        data: daily.map(d => d.port_value),
        borderColor: '#fbbf24',
        backgroundColor: 'rgba(251, 191, 36, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: '#fbbf24',
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => fmt(ctx.raw) + ' บาท' }} }}
      }},
      scales: {{
        y: {{
          ticks: {{ callback: v => (v/1000).toFixed(0) + 'k' }}
        }}
      }}
    }}
  }});

  new Chart(document.getElementById('returnChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: 'ผลตอบแทน (%)',
        data: daily.map(d => d.pnl_pct),
        borderColor: daily[daily.length-1].pnl_pct >= 0 ? '#22c55e' : '#ef4444',
        backgroundColor: daily[daily.length-1].pnl_pct >= 0
          ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ctx.raw.toFixed(2) + '%' }} }}
      }},
      scales: {{
        y: {{ ticks: {{ callback: v => v.toFixed(1) + '%' }} }}
      }}
    }}
  }});

  new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: 'ราคาทอง (บาท/บาททอง)',
        data: daily.map(d => d.price),
        borderColor: '#f59e0b',
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: '#f59e0b',
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => fmt(ctx.raw) + ' บาท' }} }}
      }},
      scales: {{
        y: {{ ticks: {{ callback: v => (v/1000).toFixed(1) + 'k' }} }}
      }}
    }}
  }});
}}
</script>
</body>
</html>"""

    out_path = BASE_DIR / "docs" / "index.html"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard saved: {out_path}")
    return str(out_path)


if __name__ == "__main__":
    generate_dashboard()
