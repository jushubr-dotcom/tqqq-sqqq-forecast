"""
Builds a Markdown forecast post from the files in outputs/.

Usage:
    python .claude/skills/generate-post/scripts/generate_post.py [--date YYYY-MM-DD] [--out PATH]

Reads:
    outputs/production_forecast.csv          (required)
    outputs/ensemble_backtest_results.csv    (optional, adds a track-record line)
"""

import argparse
import os
import sys

import pandas as pd


OUTPUT_DIR = "outputs"
PRODUCTION_PATH = os.path.join(OUTPUT_DIR, "production_forecast.csv")
ENSEMBLE_BACKTEST_PATH = os.path.join(OUTPUT_DIR, "ensemble_backtest_results.csv")

HORIZONS = [3, 5, 7, 9]
SYMBOLS = ["TQQQ", "SQQQ"]


def pct(x, signed=True):
    if pd.isna(x):
        return "n/a"
    return f"{x * 100:+.2f}%" if signed else f"{x * 100:.1f}%"


def load_latest(forecast_date):
    df = pd.read_csv(PRODUCTION_PATH, low_memory=False)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"])

    if forecast_date:
        target = pd.to_datetime(forecast_date)
        if not (df["forecast_date"] == target).any():
            available = ", ".join(sorted(df["forecast_date"].dt.strftime("%Y-%m-%d").unique()))
            sys.exit(f"No rows for forecast_date {forecast_date}. Available: {available}")
    else:
        target = df["forecast_date"].max()

    latest = df[df["forecast_date"] == target].copy()

    # A model can be run several times on the same day; the last row written wins.
    latest = latest.drop_duplicates(subset=["model_name", "stock_symbol"], keep="last")

    return target, latest


def signal_for(row, horizon):
    pred = row.get(f"{horizon}d_return_pct_pred")
    filtered = row.get(f"{horizon}d_regime_filtered_buy")

    if pd.notna(filtered):
        return "BUY" if filtered == 1 else "NO BUY"
    if pd.isna(pred):
        return "n/a"
    return "BUY" if pred > 0 else "NO BUY"


def symbol_section(latest, symbol):
    rows = latest[latest["stock_symbol"] == symbol]
    if rows.empty:
        return []

    lines = [f"### {symbol}"]

    last_close = rows["stock_end_value"].iloc[-1]
    as_of = pd.to_datetime(rows["data_as_of_date"]).max().strftime("%Y-%m-%d")
    lines.append(f"Last close ${last_close:,.2f} (data as of {as_of})")
    lines.append("")

    header = "| Model | " + " | ".join(f"{h}d return / loss prob" for h in HORIZONS) + " | 3d signal |"
    lines.append(header)
    lines.append("|" + "---|" * (len(HORIZONS) + 2))

    for _, row in rows.sort_values("model_name").iterrows():
        cells = []
        for h in HORIZONS:
            pred = row.get(f"{h}d_return_pct_pred")
            loss = row.get(f"{h}d_loss_probability")
            cells.append(f"{pct(pred)} / {pct(loss, signed=False)}")

        regime = ""
        if row.get("regime_filter_enabled") == 1:
            regime = " (regime filter on)" if row.get("regime_ok") != 0 else " (blocked by regime filter)"

        lines.append(f"| {row['model_name']} | " + " | ".join(cells) + f" | {signal_for(row, 3)}{regime} |")

    if len(rows) > 1:
        cells = []
        for h in HORIZONS:
            mean_pred = rows[f"{h}d_return_pct_pred"].mean()
            mean_loss = rows[f"{h}d_loss_probability"].mean()
            cells.append(f"**{pct(mean_pred)} / {pct(mean_loss, signed=False)}**")

        votes = int((rows["3d_return_pct_pred"] > 0).sum())
        lines.append(f"| **Average** | " + " | ".join(cells) + f" | {votes}/{len(rows)} models positive |")

    lines.append("")
    return lines


def track_record_lines():
    if not os.path.exists(ENSEMBLE_BACKTEST_PATH):
        return []

    bt = pd.read_csv(ENSEMBLE_BACKTEST_PATH)
    if bt.empty or "strategy_equity" not in bt.columns:
        return []

    last = bt.iloc[-1]
    trades = int(bt["ensemble_buy"].astype(str).str.lower().eq("true").sum())

    return [
        "### Ensemble backtest",
        f"{bt['date'].iloc[0]} to {bt['date'].iloc[-1]}: strategy {pct(last['strategy_equity'] - 1)} "
        f"vs buy-and-hold {pct(last['buy_and_hold_equity'] - 1)}, "
        f"max drawdown {pct(bt['strategy_drawdown'].min())} vs {pct(bt['buy_and_hold_drawdown'].min())}, "
        f"{trades} buy days.",
        "",
    ]


def build_post(forecast_date=None):
    target, latest = load_latest(forecast_date)

    lines = [
        f"## TQQQ / SQQQ forecast: {target.strftime('%Y-%m-%d')}",
        "",
        f"Models: {', '.join(sorted(latest['model_name'].unique()))}",
        "",
    ]

    for symbol in SYMBOLS:
        lines.extend(symbol_section(latest, symbol))

    lines.extend(track_record_lines())

    lines.append("_Cells are predicted return / probability of a loss. Model output, not financial advice._")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="forecast_date to report (default: latest)")
    parser.add_argument("--out", help="write the post here as well as stdout")
    args = parser.parse_args()

    post = build_post(args.date)

    if args.out:
        with open(args.out, "w") as f:
            f.write(post)

    print(post)


if __name__ == "__main__":
    main()
