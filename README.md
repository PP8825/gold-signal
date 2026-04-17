# Thai Gold Buy/Sell Signal → LINE

Automated technical-signal model for Thai gold (96.5% bar, baht-weight).
Checks the market every 4 hours and pushes a LINE message **only when the
signal flips** from the previous run. You will not get spam.

> ⚠️ **Not financial advice.** This is a technical-analysis research tool.
> Gold is volatile; always manage your own risk.

---

## What it does

Each run:

1. Fetches the current Thai gold bar price from goldtraders.or.th.
2. Hydrates history (first run only) from yfinance XAU/USD × USD/THB.
3. Computes three indicators: **RSI(14)**, **MACD(12/26/9)**, **MA(10/30)**.
4. Each indicator votes BUY / SELL / HOLD.
5. Final action = majority if ≥ 2 indicators agree; otherwise HOLD.
6. Compares to the last action (stored in `~/.thai_gold_signal_state.json`).
7. Pushes a LINE message **only if the action has changed** to BUY or SELL.

Example LINE message:

```
🟢 GOLD SIGNAL: BUY
──────────────
Thai Gold (96.5%): 49,850.00 THB / baht-weight
Time: 2026-04-16 21:00 (Bangkok)

Indicators
• RSI(14): 32.1 → BUY
• MACD hist: +12.40 → BUY
• MA10/MA30: 49,780 / 49,650 → BUY

Why: RSI 32.1 oversold; MACD bullish cross; MA golden cross

⚠️ Not financial advice.
```

---

## One-time setup

### 1. Install dependencies

```bash
cd <this folder>
pip install -r requirements.txt
```

### 2. Get LINE Messaging API credentials

1. Open https://developers.line.biz/console/ → log in → create a **Provider**
   if you don't have one.
2. Inside the provider, create a new **Messaging API channel**.
3. Open the channel → **Messaging API** tab → generate a
   **Channel access token (long-lived)** → copy it.
4. In the **Basic settings** tab, copy your **Your user ID** (`Uxxxxx…`).
5. Add your LINE bot as a friend by scanning its QR code (same tab),
   otherwise pushes will fail with `400 Bad Request`.

### 3. Configure credentials

```bash
cp .env.example .env
# then edit .env and paste the token + user ID
```

### 4. Test manually

```bash
./run_gold_signal.sh --force
```

`--force` makes it push to LINE even if the action didn't change, so you
can verify the integration works.

---

## Scheduling

This repo already registered a Cowork scheduled task
(`thai-gold-signal-check`) that runs every 4 hours. You can manage it from
the **Scheduled** section of the sidebar.

If you prefer a native scheduler instead:

### macOS / Linux (cron)

```bash
crontab -e
# add:
0 */4 * * * /full/path/to/run_gold_signal.sh >> /tmp/gold_signal.log 2>&1
```

### Windows (Task Scheduler)

- Action: Start a program
- Program: `python`
- Arguments: `gold_signal.py`
- Start in: the folder containing `gold_signal.py`
- Trigger: Daily, repeat every 4 hours

---

## Tuning

All parameters live at the top of `gold_signal.py` in the `CONFIG` dict:

| Setting | Default | What it does |
|---|---|---|
| `RSI_PERIOD` | 14 | RSI lookback |
| `RSI_BUY_THRESHOLD` | 35 | RSI below → BUY vote |
| `RSI_SELL_THRESHOLD` | 65 | RSI above → SELL vote |
| `MA_FAST` / `MA_SLOW` | 10 / 30 | Moving-average crossover pair |
| `MACD_FAST/SLOW/SIGNAL` | 12 / 26 / 9 | Classic MACD |
| `MIN_AGREEMENT` | 2 | At least this many votes must agree |

Make RSI thresholds tighter (e.g. 30/70) for fewer but stronger signals.

---

## Files

| File | Purpose |
|---|---|
| `gold_signal.py` | The model (indicators + LINE push) |
| `run_gold_signal.sh` | Wrapper that loads `.env` and runs the script |
| `.env.example` | Template for LINE credentials |
| `requirements.txt` | Python dependencies |
| `~/.thai_gold_signal_state.json` | Remembers last action (auto-created) |
| `~/.thai_gold_history.csv` | Appended price history (auto-created) |

---

## Troubleshooting

**`yfinance is not installed`** — run `pip install -r requirements.txt`.

**`LINE push failed (401)`** — token wrong or revoked. Regenerate.

**`LINE push failed (400)`** — your `LINE_TO` ID is wrong, or you haven't
added the bot as a friend. Open the channel's QR code and scan it.

**`Not enough history`** — first run bootstraps from yfinance; needs
internet. If yfinance fails, the script can't run until enough Thai spot
samples have accumulated in the history CSV (~30 runs).

**HTML parse failed** — goldtraders.or.th changed their page markup. The
script falls back to yfinance-derived Thai prices automatically.
