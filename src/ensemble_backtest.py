import os
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OUTPUT_DIR = "outputs"

BACKTEST_INPUT_PATH = os.path.join(OUTPUT_DIR, "backtest_results.csv")
ENSEMBLE_BACKTEST_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "ensemble_backtest_results.csv",
)

HORIZONS = [3, 5, 7, 9]

# Use all models first.
# Later you can restrict this list to only the strongest models.
MODEL_NAMES_TO_INCLUDE = [
    "RandomForest",
    "ExtraTrees",
    "XGBoost",
    "LightGBM",
    "CatBoost",
    "Ridge",
    "ElasticNet",
]

# Minimum number of model predictions required for a row to be ensembled.
# Example:
# If 7 models exist but only 4 produced predictions for a date, still ensemble.
MIN_MODELS_REQUIRED = 3


# ============================================================
# HELPERS
# ============================================================

def safe_divide(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def get_best_backtest_per_model(df):
    """
    Optional but recommended.

    Your CSV contains multiple backtest_name parameter combinations per model.
    If you ensemble all parameter combinations, models with more parameter rows
    will dominate the ensemble.

    This function chooses one best backtest_name per model_name using:
        1. Highest overall_buy_profit_pct
        2. Minimum positive prediction count filter
    """

    summary = (
        df.groupby(["model_name", "backtest_name"], dropna=False)
        .agg(
            avg_overall_buy_profit_pct=("overall_buy_profit_pct", "mean"),
            total_pred_positive=("sum_count_pred_positive", "sum"),
            total_pred_positive_actual_positive=(
                "sum_count_pred_positive_w_actual_positive",
                "sum",
            ),
            row_count=("symbol", "size"),
        )
        .reset_index()
    )

    summary["true_overall_buy_profit_pct"] = summary.apply(
        lambda r: safe_divide(
            r["total_pred_positive_actual_positive"],
            r["total_pred_positive"],
        ),
        axis=1,
    )

    # Avoid selecting a model variant that only made a tiny number of buy calls.
    MIN_POSITIVE_PREDICTIONS = int(os.getenv("MIN_POSITIVE_PREDICTIONS", "30"))

    summary = summary[summary["total_pred_positive"] >= MIN_POSITIVE_PREDICTIONS].copy()
    
    if summary.empty:
        print(
            f"No model/backtest combinations passed MIN_POSITIVE_PREDICTIONS="
            f"{MIN_POSITIVE_PREDICTIONS}. Falling back to best available combinations."
        )
    
        summary = (
            df.groupby(["model_name", "backtest_name"], dropna=False)
            .agg(
                avg_overall_buy_profit_pct=("overall_buy_profit_pct", "mean"),
                total_pred_positive=("sum_count_pred_positive", "sum"),
                total_pred_positive_actual_positive=(
                    "sum_count_pred_positive_w_actual_positive",
                    "sum",
                ),
                row_count=("symbol", "size"),
            )
            .reset_index()
        )
    
        summary["true_overall_buy_profit_pct"] = summary.apply(
            lambda r: safe_divide(
                r["total_pred_positive_actual_positive"],
                r["total_pred_positive"],
            ),
            axis=1,
        )

    summary = summary.sort_values(
        ["model_name", "true_overall_buy_profit_pct", "total_pred_positive"],
        ascending=[True, False, False],
    )

    best = summary.groupby("model_name").head(1).reset_index(drop=True)

    return best


def filter_to_best_backtests(df, best_backtests):
    keep_pairs = set(
        zip(best_backtests["model_name"], best_backtests["backtest_name"])
    )

    filtered = df[
        df.apply(
            lambda r: (r["model_name"], r["backtest_name"]) in keep_pairs,
            axis=1,
        )
    ].copy()

    return filtered


def build_long_horizon_backtest(df):
    """
    Converts wide backtest rows into long format:

    one row per:
        model_name
        backtest_name
        symbol
        test_start_date
        horizon
    """

    long_rows = []

    for horizon in HORIZONS:
        pred_col = f"{horizon}d_return_pct_pred"
        actual_col = f"{horizon}d_return_pct_actual"
        close_actual_col = f"{horizon}d_close_actual"
        conf_col = f"{horizon}d_confidence_no_loss"
        loss_col = f"{horizon}d_loss_probability"

        required_cols = [
            pred_col,
            actual_col,
            close_actual_col,
            conf_col,
            loss_col,
        ]

        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            print(f"Skipping {horizon}d because missing columns: {missing_cols}")
            continue

        temp = df[
            [
                "run_timestamp",
                "model_name",
                "backtest_name",
                "symbol",
                "test_start_date",
                "test_end_date",
                "previous_trading_date",
                "previous_close_before_test_start",
                pred_col,
                actual_col,
                close_actual_col,
                conf_col,
                loss_col,
            ]
        ].copy()

        temp["horizon"] = horizon

        temp = temp.rename(
            columns={
                pred_col: "return_pct_pred",
                actual_col: "return_pct_actual",
                close_actual_col: "close_actual",
                conf_col: "confidence_no_loss",
                loss_col: "loss_probability",
            }
        )

        long_rows.append(temp)

    if not long_rows:
        return pd.DataFrame()

    long_df = pd.concat(long_rows, ignore_index=True)

    long_df = long_df.dropna(
        subset=[
            "return_pct_pred",
            "return_pct_actual",
            "loss_probability",
        ]
    )

    return long_df


def create_backtest_ensemble(long_df):
    """
    Creates simple average ensemble by symbol/date/horizon.
    """

    group_cols = [
        "symbol",
        "test_start_date",
        "horizon",
    ]

    ensemble = (
        long_df.groupby(group_cols)
        .agg(
            model_count=("model_name", "nunique"),
            models_used=("model_name", lambda x: ",".join(sorted(set(x)))),
            backtests_used=("backtest_name", lambda x: ",".join(sorted(set(x)))),
            previous_trading_date=("previous_trading_date", "first"),
            previous_close_before_test_start=(
                "previous_close_before_test_start",
                "first",
            ),
            test_end_date=("test_end_date", "max"),
            ensemble_return_pct_pred=("return_pct_pred", "mean"),
            ensemble_return_pct_actual=("return_pct_actual", "first"),
            ensemble_close_actual=("close_actual", "first"),
            ensemble_loss_probability=("loss_probability", "mean"),
        )
        .reset_index()
    )

    ensemble = ensemble[ensemble["model_count"] >= MIN_MODELS_REQUIRED].copy()

    ensemble["ensemble_confidence_no_loss"] = (
        1 - ensemble["ensemble_loss_probability"]
    )

    ensemble["ensemble_count_pred_positive"] = (
        ensemble["ensemble_return_pct_pred"] > 0
    ).astype(int)

    ensemble["ensemble_count_pred_positive_w_actual_positive"] = (
        (ensemble["ensemble_return_pct_pred"] > 0)
        & (ensemble["ensemble_return_pct_actual"] > 0)
    ).astype(int)

    ensemble["ensemble_buy_profit_pct"] = ensemble.apply(
        lambda r: safe_divide(
            r["ensemble_count_pred_positive_w_actual_positive"],
            r["ensemble_count_pred_positive"],
        ),
        axis=1,
    )

    return ensemble


def summarise_ensemble(ensemble):
    """
    Summarises ensemble performance by horizon and symbol.
    """

    summary = (
        ensemble.groupby(["symbol", "horizon"])
        .agg(
            rows=("symbol", "size"),
            avg_model_count=("model_count", "mean"),
            avg_pred_return=("ensemble_return_pct_pred", "mean"),
            avg_actual_return=("ensemble_return_pct_actual", "mean"),
            sum_count_pred_positive=("ensemble_count_pred_positive", "sum"),
            sum_count_pred_positive_w_actual_positive=(
                "ensemble_count_pred_positive_w_actual_positive",
                "sum",
            ),
            avg_loss_probability=("ensemble_loss_probability", "mean"),
        )
        .reset_index()
    )

    summary["overall_buy_profit_pct"] = summary.apply(
        lambda r: safe_divide(
            r["sum_count_pred_positive_w_actual_positive"],
            r["sum_count_pred_positive"],
        ),
        axis=1,
    )

    summary = summary.sort_values(
        ["symbol", "horizon"]
    ).reset_index(drop=True)

    return summary


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.exists(BACKTEST_INPUT_PATH):
        raise FileNotFoundError(f"Missing input file: {BACKTEST_INPUT_PATH}")

    df = pd.read_csv(BACKTEST_INPUT_PATH, low_memory=False)

    df = df[df["model_name"].isin(MODEL_NAMES_TO_INCLUDE)].copy()

    if df.empty:
        raise ValueError("No rows found for selected model names.")

    print("Selecting best backtest_name per model...")
    best_backtests = get_best_backtest_per_model(df)

    print("\nBest backtest per model:")
    print(best_backtests)

    df_best = filter_to_best_backtests(df, best_backtests)

    print(f"\nRows after filtering to best backtests: {len(df_best):,}")

    long_df = build_long_horizon_backtest(df_best)

    print(f"Long-format rows: {len(long_df):,}")

    ensemble = create_backtest_ensemble(long_df)

    print(f"Ensemble rows: {len(ensemble):,}")

    ensemble.to_csv(ENSEMBLE_BACKTEST_OUTPUT_PATH, index=False)

    print(f"\nSaved ensemble backtest to: {ENSEMBLE_BACKTEST_OUTPUT_PATH}")

    summary = summarise_ensemble(ensemble)

    print("\nEnsemble summary:")
    print(summary)


if __name__ == "__main__":
    main()
