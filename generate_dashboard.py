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

    pnl_color = "#5a9e6f" if pnl >= 0 else "#c97b7b"
    pnl_sign = "+" if pnl >= 0 else ""

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gold Portfolio Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background: #f8f6f3;
    color: #4a4543;
    min-height: 100vh;
    font-weight: 300;
  }}
  .header {{
    background: #fffdf9;
    border-bottom: 1px solid #e8e4df;
    padding: 24px 28px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .header h1 {{
    font-size: 1.3rem;
    font-weight: 500;
    color: #6b5c4c;
    letter-spacing: -0.01em;
  }}
  .header .period {{
    color: #a09890;
    font-size: 0.8rem;
    font-weight: 400;
    margin-top: 2px;
  }}
  .updated {{
    color: #b5aea6;
    font-size: 0.75rem;
  }}
  .sync-btn {{
    background: #efe9e1;
    color: #7a6e62;
    border: 1px solid #ddd6cd;
    padding: 7px 14px;
    border-radius: 20px;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 500;
    font-family: inherit;
    display: flex;
    align-items: center;
    gap: 5px;
    transition: all 0.2s;
  }}
  .sync-btn:hover {{ background: #e5ddd4; }}
  .sync-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  .sync-btn .spinner {{
    display: inline-block;
    width: 12px; height: 12px;
    border: 1.5px solid #7a6e62;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .footer {{
    text-align: center;
    padding: 28px;
    color: #c4bdb5;
    font-size: 0.7rem;
    letter-spacing: 0.03em;
    margin-top: 40px;
  }}
  .container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px;
  }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-bottom: 20px;
  }}
  .card {{
    background: #fffdf9;
    border: 1px solid #e8e4df;
    border-radius: 14px;
    padding: 18px;
  }}
  .card .label {{
    color: #a09890;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 500;
    margin-bottom: 8px;
  }}
  .card .value {{
    font-size: 1.4rem;
    font-weight: 600;
    color: #4a4543;
  }}
  .card .sub {{
    color: #b5aea6;
    font-size: 0.75rem;
    margin-top: 4px;
    font-weight: 400;
  }}
  .green {{ color: #5a9e6f; }}
  .red {{ color: #c97b7b; }}
  .gold {{ color: #b8956a; }}
  .chart-container {{
    background: #fffdf9;
    border: 1px solid #e8e4df;
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 20px;
  }}
  .chart-container h2 {{
    font-size: 0.85rem;
    font-weight: 500;
    color: #7a6e62;
    margin-bottom: 14px;
  }}
  .chart-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 20px;
  }}
  @media (max-width: 768px) {{
    .chart-row {{ grid-template-columns: 1fr; }}
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }}
  th {{
    background: #f0ebe5;
    color: #7a6e62;
    padding: 10px 12px;
    text-align: center;
    font-weight: 500;
    position: sticky;
    top: 0;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}
  td {{
    padding: 9px 12px;
    text-align: center;
    border-bottom: 1px solid #f0ebe5;
    color: #5c5550;
  }}
  tr:nth-child(even) {{ background: #faf8f5; }}
  tr:nth-child(odd) {{ background: #fffdf9; }}
  .buy-row {{ background: #f3f9f4 !important; }}
  .sell-row {{ background: #faf3f3 !important; }}
  .badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-weight: 500;
    font-size: 0.7rem;
    letter-spacing: 0.02em;
  }}
  .badge-buy {{ background: #e4f2e7; color: #5a9e6f; }}
  .badge-sell {{ background: #f5e5e5; color: #c97b7b; }}
  .table-scroll {{
    max-height: 400px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid #e8e4df;
  }}
  .tabs {{
    display: flex;
    gap: 6px;
    margin-bottom: 14px;
  }}
  .tab {{
    padding: 8px 18px;
    background: #fffdf9;
    border: 1px solid #e8e4df;
    border-radius: 20px;
    color: #a09890;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 400;
    font-family: inherit;
    transition: all 0.2s;
  }}
  .tab.active {{
    background: #6b5c4c;
    color: #fffdf9;
    border-color: #6b5c4c;
  }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .stat-row {{
    display: flex;
    justify-content: space-between;
    padding: 9px 0;
    border-bottom: 1px solid #f0ebe5;
  }}
  .stat-row:last-child {{ border-bottom: none; }}
  .stat-label {{ color: #a09890; font-weight: 400; }}
  .stat-value {{ font-weight: 500; }}
  .allocation-bar {{
    display: flex;
    height: 24px;
    border-radius: 12px;
    overflow: hidden;
    margin-top: 10px;
  }}
  .alloc-cash {{
    background: #b8cfe0;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    font-weight: 500;
    transition: width 0.5s;
  }}
  .alloc-gold {{
    background: #dcc6a0;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.65rem;
    font-weight: 500;
    transition: width 0.5s;
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Gold Portfolio</h1>
    <div class="period">{test_start} — {test_end}</div>
  </div>
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <div class="updated">{now.strftime("%Y-%m-%d %H:%M")} ICT</div>
    <button class="sync-btn" id="syncBtn" onclick="triggerSync()">
      Sync
    </button>
  </div>
</div>

<div class="container">

  <div class="cards">
    <div class="card">
      <div class="label">Portfolio Value</div>
      <div class="value gold">{port_value:,.2f}</div>
      <div class="sub">from {initial:,.0f}</div>
    </div>
    <div class="card">
      <div class="label">P&L</div>
      <div class="value" style="color:{pnl_color}">{pnl_sign}{pnl:,.2f}</div>
      <div class="sub" style="color:{pnl_color}">{pnl_sign}{pnl_pct:.2f}%</div>
    </div>
    <div class="card">
      <div class="label">Gold Price</div>
      <div class="value">{price:,.2f}</div>
      <div class="sub">THB / baht-weight</div>
    </div>
    <div class="card">
      <div class="label">Avg Cost</div>
      <div class="value">{avg_cost:,.2f}</div>
      <div class="sub">{"no gold held" if gold < 0.01 else f"holding {gold:.4f}"}</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:20px">
    <div class="label">Allocation</div>
    <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:0.8rem;color:#7a6e62">
      <span>Cash: {cash:,.2f}</span>
      <span>Gold: {gold * price:,.2f}</span>
    </div>
    <div class="allocation-bar">
      <div class="alloc-cash" style="width:{cash/port_value*100 if port_value > 0 else 100:.0f}%">
        {cash/port_value*100 if port_value > 0 else 100:.0f}%
      </div>
      <div class="alloc-gold" style="width:{gold*price/port_value*100 if port_value > 0 else 0:.0f}%">
        {f"{gold*price/port_value*100:.0f}%" if gold > 0.01 else ""}
      </div>
    </div>
  </div>

  <div class="cards" style="grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))">
    <div class="card">
      <div class="label">Trade Stats</div>
      <div class="stat-row"><span class="stat-label">Total trades</span><span class="stat-value">{len(trades)}</span></div>
      <div class="stat-row"><span class="stat-label">Pairs</span><span class="stat-value">{pairs}</span></div>
      <div class="stat-row"><span class="stat-label">Win / Loss</span><span class="stat-value"><span class="green">{wins}</span> / <span class="red">{pairs - wins}</span></span></div>
      <div class="stat-row"><span class="stat-label">Win rate</span><span class="stat-value">{win_rate:.0f}%</span></div>
    </div>
    <div class="card">
      <div class="label">Profit / Loss</div>
      <div class="stat-row"><span class="stat-label">Gross profit</span><span class="stat-value green">+{total_profit:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">Gross loss</span><span class="stat-value red">-{total_loss:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">Net</span><span class="stat-value" style="color:{pnl_color}">{pnl_sign}{total_profit - total_loss:,.2f}</span></div>
      <div class="stat-row"><span class="stat-label">Rule</span><span class="stat-value" style="font-size:0.7rem;color:#a09890">No sell below cost</span></div>
    </div>
  </div>

  <div class="chart-row">
    <div class="chart-container">
      <h2>Portfolio Value</h2>
      <canvas id="valueChart"></canvas>
    </div>
    <div class="chart-container">
      <h2>Return (%)</h2>
      <canvas id="returnChart"></canvas>
    </div>
  </div>

  <div class="chart-container">
    <h2>Gold Price</h2>
    <canvas id="priceChart"></canvas>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('trades')">Trades ({len(trades)})</div>
    <div class="tab" onclick="switchTab('daily')">Daily ({len(daily_history)})</div>
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
  const pcolor = d.pnl >= 0 ? '#5a9e6f' : '#c97b7b';
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

Chart.defaults.color = '#a09890';
Chart.defaults.borderColor = '#e8e4df';

if (daily.length >= 1) {{
  const labels = daily.map(d => d.date.slice(5));

  new Chart(document.getElementById('valueChart'), {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: 'มูลค่าพอร์ต (บาท)',
        data: daily.map(d => d.port_value),
        borderColor: '#b8956a',
        backgroundColor: 'rgba(184, 149, 106, 0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: '#b8956a',
        borderWidth: 2,
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
        borderColor: daily[daily.length-1].pnl_pct >= 0 ? '#5a9e6f' : '#c97b7b',
        backgroundColor: daily[daily.length-1].pnl_pct >= 0
          ? 'rgba(90,158,111,0.08)' : 'rgba(201,123,123,0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        borderWidth: 2,
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
        borderColor: '#c9a96e',
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: '#c9a96e',
        borderWidth: 2,
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

// Sync button — refresh page to get latest data (cache-busting)
function triggerSync() {{
  const btn = document.getElementById('syncBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Updating...';
  // Cache-bust reload to get freshest version from GitHub Pages
  location.href = location.pathname + '?t=' + Date.now();
}}
</script>

<div class="footer">
  Test by PP | Gold Forward Test {test_start} → {test_end} | Powered by GitHub Actions
</div>

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
