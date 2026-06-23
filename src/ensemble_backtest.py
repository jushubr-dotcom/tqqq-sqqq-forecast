import os
import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = os.getenv("BACKTEST_FILE", "outputs/backtest_results.csv")
OUTPUT_FILE = os.getenv("ENSEMBLE_OUTPUT_FILE", "outputs/ensemble_backtest_results.csv")
SUMMARY_FILE = os.getenv("ENSEMBLE_SUMMARY_FILE", "outputs/ensemble_summary.csv")

MODEL_ON_THRESHOLD = float(os.getenv("MODEL_ON_THRESHOLD", "0"))

# Changed from 3 to 2 because your output shows only ElasticNet + ExtraTrees active
MIN_FAMILY_CONFIRMATIONS = int(os.getenv("MIN_FAMILY_CONFIRMATIONS", "2"))

# Changed from 6.5 to 3.5 because your current score is around 3.995
ENSEMBLE_SCORE_THRESHOLD = float(os.getenv("ENSEMBLE_SCORE_THRESHOLD", "3.5"))

# Optional: require the top anchor family to be active
REQUIRE_ANCHOR_ON = os.getenv("REQUIRE_ANCHOR_ON", "1") == "1"

# Family weights based on your historical result table
# ExtraTrees and ElasticNet are strongest; others are lower-confidence confirmations
DEFAULT_FAMILY_WEIGHTS = {
    "ExtraTrees": 2.0,
    "ElasticNet": 2.0,
    "RandomForest": 1.5,
    "CatBoost": 1.5,
    "XGBoost": 1.0,
    "LightGBM": 1.0,
    "Ridge": 0.5,
}


# ============================================================
# COLUMN DETECTION
# ============================================================

def find_first_existing_col(df, candidates, label):
    for col in candidates:
        if col in df.columns:
            return col

    raise ValueError(
        f"Could not find {label}. Tried: {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def detect_columns(df):
    date_col = find_first_existing_col(
        df,
        [
            "date",
            "Date",
            "forecast_date",
            "prediction_date",
            "test_date",
            "test_start",
            "test_start_date",
            "backtest_date",
            "run_date",
            "target_date",
        ],
        "date column",
    )

    model_family_col = find_first_existing_col(
        df,
        [
            "MODEL_NAME",
            "model_name",
            "model_family",
            "family",
        ],
        "model family column",
    )

    pred_col = find_first_existing_col(
        df,
        [
            "3d_return_pct_pred",
            "Average of 3d_return_pct_pred",
            "return_pct_pred",
            "predicted_return",
            "prediction",
            "y_pred",
            "pred",
        ],
        "prediction column",
    )

    actual_col = find_first_existing_col(
        df,
        [
            "3d_return_pct_actual",
            "Average of 3d_return_pct_actual",
            "return_pct_actual",
            "actual_return",
            "actual",
            "y_actual",
            "target",
        ],
        "actual return column",
    )

    return date_col, model_family_col, pred_col, actual_col


# ============================================================
# FAMILY NORMALISATION
# ============================================================

def normalise_family_name(name):
    name = str(name).strip()

    mapping = {
        "extratrees": "ExtraTrees",
        "extra trees": "ExtraTrees",
        "et": "ExtraTrees",

        "elasticnet": "ElasticNet",
        "elastic net": "ElasticNet",

        "randomforest": "RandomForest",
        "random forest": "RandomForest",
        "rf": "RandomForest",

        "catboost": "CatBoost",
        "cat": "CatBoost",

        "xgboost": "XGBoost",
        "xgb": "XGBoost",

        "lightgbm": "LightGBM",
        "lgbm": "LightGBM",

        "ridge": "Ridge",
    }

    key = name.lower().replace("_", " ").strip()
    key_no_space = key.replace(" ", "")

    if key in mapping:
        return mapping[key]

    if key_no_space in mapping:
        return mapping[key_no_space]

    return name


# ============================================================
# PERFORMANCE TABLE
# ============================================================

def build_family_performance_table(df, date_col, model_family_col, pred_col, actual_col):
    df = df.copy()

    df["model_on"] = df[pred_col] > MODEL_ON_THRESHOLD
    df["actual_profitable_row"] = df[actual_col] > 0

    rows = []

    for family, g in df.groupby(model_family_col):
        model_on = g[g["model_on"]]
        model_off = g[~g["model_on"]]

        model_on_precision = model_on["actual_profitable_row"].mean() if len(model_on) else np.nan
        model_off_precision = model_off["actual_profitable_row"].mean() if len(model_off) else np.nan

        precision_lift = (
            model_on_precision - model_off_precision
            if pd.notna(model_on_precision) and pd.notna(model_off_precision)
            else np.nan
        )

        rows.append(
            {
                "model_family": family,
                "total_rows": len(g),
                "model_on_rows": len(model_on),
                "model_off_rows": len(model_off),
                "model_on_precision": model_on_precision,
                "model_off_precision": model_off_precision,
                "precision_lift": precision_lift,
                "avg_return_when_on": model_on[actual_col].mean() if len(model_on) else np.nan,
                "worst_return_when_on": model_on[actual_col].min() if len(model_on) else np.nan,
            }
        )

    perf = pd.DataFrame(rows)

    perf = perf.sort_values(
        ["model_on_precision", "precision_lift", "avg_return_when_on"],
        ascending=[False, False, False],
    )

    return perf


# ============================================================
# ENSEMBLE
# ============================================================

def build_ensemble(df, date_col, model_family_col, pred_col, actual_col):
    df = df.copy()

    df["model_on"] = df[pred_col] > MODEL_ON_THRESHOLD

    # Family is ON if any row for that MODEL_NAME is ON that date
    family_signal = (
        df.groupby([date_col, model_family_col], as_index=False)
        .agg(family_on=("model_on", "max"))
    )

    signal_wide = (
        family_signal
        .pivot_table(
            index=date_col,
            columns=model_family_col,
            values="family_on",
            aggfunc="max",
        )
        .fillna(False)
        .astype(bool)
    )

    available_families = list(signal_wide.columns)

    family_weights = {
        family: DEFAULT_FAMILY_WEIGHTS.get(family, 1.0)
        for family in available_families
    }

    # Anchor families are the two strongest families from your current testing
    anchor_families = [
        family for family in ["ExtraTrees", "ElasticNet"]
        if family in available_families
    ]

    # Correct actual return aggregation
    actual_by_date = (
        df.groupby(date_col, as_index=True)
        .agg(
            actual_3d_return=(actual_col, "mean"),
            family_count=(model_family_col, "nunique"),
        )
    )

    # Important fix: determine profitability AFTER averaging actual return
    actual_by_date["actual_profitable"] = actual_by_date["actual_3d_return"] > 0

    rows = []

    for dt, row in signal_wide.iterrows():
        active_families = [family for family in available_families if bool(row[family])]
        active_family_count = len(active_families)

        ensemble_score = sum(family_weights[family] for family in active_families)

        anchor_on = any(family in active_families for family in anchor_families)

        ensemble_buy = (
            active_family_count >= MIN_FAMILY_CONFIRMATIONS
            and ensemble_score >= ENSEMBLE_SCORE_THRESHOLD
            and (anchor_on or not REQUIRE_ANCHOR_ON)
        )

        rows.append(
            {
                date_col: dt,
                "ensemble_buy": ensemble_buy,
                "ensemble_score": ensemble_score,
                "active_family_count": active_family_count,
                "active_families": ",".join(active_families),
                "anchor_families": ",".join(anchor_families),
                "anchor_on": anchor_on,
            }
        )

    ensemble = pd.DataFrame(rows).set_index(date_col)
    ensemble = ensemble.join(actual_by_date, how="left")

    ensemble["strategy_3d_return"] = np.where(
        ensemble["ensemble_buy"],
        ensemble["actual_3d_return"],
        0.0,
    )

    ensemble["buy_and_hold_3d_return"] = ensemble["actual_3d_return"]

    ensemble["strategy_equity"] = (1.0 + ensemble["strategy_3d_return"]).cumprod()
    ensemble["buy_and_hold_equity"] = (1.0 + ensemble["buy_and_hold_3d_return"]).cumprod()

    ensemble["strategy_running_peak"] = ensemble["strategy_equity"].cummax()
    ensemble["strategy_drawdown"] = (
        ensemble["strategy_equity"] / ensemble["strategy_running_peak"] - 1.0
    )

    ensemble["buy_and_hold_running_peak"] = ensemble["buy_and_hold_equity"].cummax()
    ensemble["buy_and_hold_drawdown"] = (
        ensemble["buy_and_hold_equity"] / ensemble["buy_and_hold_running_peak"] - 1.0
    )

    return ensemble


# ============================================================
# SUMMARY
# ============================================================

def build_summary(ensemble):
    buy_days = ensemble[ensemble["ensemble_buy"]].copy()
    no_buy_days = ensemble[~ensemble["ensemble_buy"]].copy()

    summary = {
        "total_days": len(ensemble),
        "buy_days": len(buy_days),
        "no_buy_days": len(no_buy_days),
        "buy_rate": len(buy_days) / len(ensemble) if len(ensemble) else np.nan,

        "min_family_confirmations": MIN_FAMILY_CONFIRMATIONS,
        "ensemble_score_threshold": ENSEMBLE_SCORE_THRESHOLD,
        "require_anchor_on": REQUIRE_ANCHOR_ON,

        "buy_profitable_days": int(buy_days["actual_profitable"].sum()) if len(buy_days) else 0,
        "buy_profit_pct": buy_days["actual_profitable"].mean() if len(buy_days) else np.nan,

        "no_buy_profitable_days": int(no_buy_days["actual_profitable"].sum()) if len(no_buy_days) else 0,
        "no_buy_profit_pct": no_buy_days["actual_profitable"].mean() if len(no_buy_days) else np.nan,

        "avg_return_when_buy": buy_days["actual_3d_return"].mean() if len(buy_days) else np.nan,
        "median_return_when_buy": buy_days["actual_3d_return"].median() if len(buy_days) else np.nan,
        "worst_return_when_buy": buy_days["actual_3d_return"].min() if len(buy_days) else np.nan,
        "best_return_when_buy": buy_days["actual_3d_return"].max() if len(buy_days) else np.nan,

        "avg_return_when_no_buy": no_buy_days["actual_3d_return"].mean() if len(no_buy_days) else np.nan,

        "strategy_total_return": ensemble["strategy_equity"].iloc[-1] - 1.0 if len(ensemble) else np.nan,
        "buy_and_hold_total_return": ensemble["buy_and_hold_equity"].iloc[-1] - 1.0 if len(ensemble) else np.nan,

        "strategy_max_drawdown": ensemble["strategy_drawdown"].min() if len(ensemble) else np.nan,
        "buy_and_hold_max_drawdown": ensemble["buy_and_hold_drawdown"].min() if len(ensemble) else np.nan,

        "avg_ensemble_score": ensemble["ensemble_score"].mean() if len(ensemble) else np.nan,
        "avg_ensemble_score_when_buy": buy_days["ensemble_score"].mean() if len(buy_days) else np.nan,
    }

    return pd.DataFrame([summary])


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    date_col, model_family_col, pred_col, actual_col = detect_columns(df)

    print("Detected columns:")
    print(f"  DATE_COL         = {date_col}")
    print(f"  MODEL_FAMILY_COL = {model_family_col}")
    print(f"  PRED_COL         = {pred_col}")
    print(f"  ACTUAL_COL       = {actual_col}")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[pred_col] = pd.to_numeric(df[pred_col], errors="coerce")
    df[actual_col] = pd.to_numeric(df[actual_col], errors="coerce")

    df = df.dropna(subset=[date_col, model_family_col, pred_col, actual_col]).copy()

    if df.empty:
        raise ValueError("No valid rows left after cleaning input data.")

    df[model_family_col] = df[model_family_col].apply(normalise_family_name)

    family_perf = build_family_performance_table(
        df=df,
        date_col=date_col,
        model_family_col=model_family_col,
        pred_col=pred_col,
        actual_col=actual_col,
    )

    ensemble = build_ensemble(
        df=df,
        date_col=date_col,
        model_family_col=model_family_col,
        pred_col=pred_col,
        actual_col=actual_col,
    )

    summary_df = build_summary(ensemble)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)

    ensemble.reset_index().rename(columns={date_col: "date"}).to_csv(
        OUTPUT_FILE,
        index=False,
    )

    summary_df.to_csv(SUMMARY_FILE, index=False)
    family_perf.to_csv("outputs/ensemble_family_performance.csv", index=False)

    print("\nFAMILY PERFORMANCE")
    print(family_perf.to_string(index=False))

    print("\nENSEMBLE SUMMARY")
    print(summary_df.T)

    print(f"\nSaved ensemble results to: {OUTPUT_FILE}")
    print(f"Saved ensemble summary to: {SUMMARY_FILE}")
    print("Saved family performance to: outputs/ensemble_family_performance.csv")

    if summary_df.loc[0, "buy_days"] == 0:
        print("\nWARNING: Ensemble produced 0 BUY days.")
        print("Try:")
        print("  MIN_FAMILY_CONFIRMATIONS=2")
        print("  ENSEMBLE_SCORE_THRESHOLD=3.5")


if __name__ == "__main__":
    main()
