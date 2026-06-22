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

MODEL_NAMES_TO_INCLUDE = [
    "RandomForest",
    "ExtraTrees",
    "XGBoost",
    "LightGBM",
    "CatBoost",
    "Ridge",
    "ElasticNet",
]

MIN_MODELS_REQUIRED = int(os.getenv("MIN_MODELS_REQUIRED", "3"))
MIN_POSITIVE_PREDICTIONS = int(os.getenv("MIN_POSITIVE_PREDICTIONS", "30"))
BUY_RETURN_THRESHOLD = float(os.getenv("BUY_RETURN_THRESHOLD", "0.0"))
WEIGHTED_BUY_SCORE_THRESHOLD = float(os.getenv("WEIGHTED_BUY_SCORE_THRESHOLD", "0.60"))

MODEL_SELECTION_METRIC = os.getenv("MODEL_SELECTION_METRIC", "return_uplift")

DEFAULT_MODEL_WEIGHTS = {
    "ExtraTrees": 0.40,
    "LightGBM": 0.25,
    "XGBoost": 0.12,
    "RandomForest": 0.10,
    "CatBoost": 0.07,
    "Ridge": 0.03,
    "ElasticNet": 0.03,
}

USE_BACKTEST_DERIVED_WEIGHTS = (
    os.getenv("USE_BACKTEST_DERIVED_WEIGHTS", "true").lower() == "true"
)


# ============================================================
# HELPERS
# ============================================================

def safe_divide(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def require_columns(df, cols, context):
    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns for {context}: {missing_cols}")


def get_best_backtest_per_model(df):
    """
    Chooses one best backtest_name per model_name.

    Priority:
      1. Highest model-on return uplift over model-off baseline
      2. Highest model-on profitable rate uplift
      3. Higher positive prediction count
    """

    required_cols = [
        "model_name",
        "backtest_name",
        "sum_count_pred_positive",
        "sum_count_pred_positive_w_actual_positive",
        "average_return_pct_model_on_numerator",
        "average_return_pct_model_on_denominator",
        "average_return_pct_model_off_numerator",
        "average_return_pct_model_off_denominator",
        "average_profitable_model_on_numerator",
        "average_profitable_model_on_denominator",
        "average_profitable_model_off_numerator",
        "average_profitable_model_off_denominator",
    ]
    require_columns(df, required_cols, "best backtest selection")

    summary = (
        df.groupby(["model_name", "backtest_name"], dropna=False)
        .agg(
            total_pred_positive=("sum_count_pred_positive", "sum"),
            total_pred_positive_actual_positive=(
                "sum_count_pred_positive_w_actual_positive",
                "sum",
            ),
            model_on_return_num=("average_return_pct_model_on_numerator", "sum"),
            model_on_return_den=("average_return_pct_model_on_denominator", "sum"),
            model_off_return_num=("average_return_pct_model_off_numerator", "sum"),
            model_off_return_den=("average_return_pct_model_off_denominator", "sum"),
            model_on_profitable_num=("average_profitable_model_on_numerator", "sum"),
            model_on_profitable_den=("average_profitable_model_on_denominator", "sum"),
            model_off_profitable_num=("average_profitable_model_off_numerator", "sum"),
            model_off_profitable_den=("average_profitable_model_off_denominator", "sum"),
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

    summary["return_pct_model_on"] = summary.apply(
        lambda r: safe_divide(r["model_on_return_num"], r["model_on_return_den"]),
        axis=1,
    )
    summary["return_pct_model_off"] = summary.apply(
        lambda r: safe_divide(r["model_off_return_num"], r["model_off_return_den"]),
        axis=1,
    )
    summary["return_pct_model_uplift"] = (
        summary["return_pct_model_on"] - summary["return_pct_model_off"]
    )

    summary["profitable_model_on"] = summary.apply(
        lambda r: safe_divide(r["model_on_profitable_num"], r["model_on_profitable_den"]),
        axis=1,
    )
    summary["profitable_model_off"] = summary.apply(
        lambda r: safe_divide(r["model_off_profitable_num"], r["model_off_profitable_den"]),
        axis=1,
    )
    summary["profitable_model_uplift"] = (
        summary["profitable_model_on"] - summary["profitable_model_off"]
    )

    filtered = summary[summary["total_pred_positive"] >= MIN_POSITIVE_PREDICTIONS].copy()

    if filtered.empty:
        print(
            f"No model/backtest combinations passed MIN_POSITIVE_PREDICTIONS="
            f"{MIN_POSITIVE_PREDICTIONS}. Falling back to best available combinations."
        )
        filtered = summary.copy()

    if MODEL_SELECTION_METRIC == "buy_profit":
        sort_cols = [
            "model_name",
            "true_overall_buy_profit_pct",
            "return_pct_model_uplift",
            "total_pred_positive",
        ]
    else:
        sort_cols = [
            "model_name",
            "return_pct_model_uplift",
            "profitable_model_uplift",
            "total_pred_positive",
        ]

    filtered = filtered.sort_values(
        sort_cols,
        ascending=[True, False, False, False],
    )

    return filtered.groupby("model_name").head(1).reset_index(drop=True)


def build_model_weights(best_backtests):
    """
    Builds model weights after best variant selection.

    If USE_BACKTEST_DERIVED_WEIGHTS=true, weights are proportional to positive return uplift.
    Otherwise, DEFAULT_MODEL_WEIGHTS are used and normalised over included models.
    """

    if USE_BACKTEST_DERIVED_WEIGHTS:
        temp = best_backtests.copy()
        temp["positive_uplift"] = temp["return_pct_model_uplift"].clip(lower=0)
        temp["raw_weight"] = temp["positive_uplift"] + 0.001
        total_raw_weight = temp["raw_weight"].sum()

        if total_raw_weight > 0:
            return {
                row["model_name"]: row["raw_weight"] / total_raw_weight
                for _, row in temp.iterrows()
            }

    included_default_weights = {
        model_name: DEFAULT_MODEL_WEIGHTS.get(model_name, 0.01)
        for model_name in best_backtests["model_name"].unique()
    }

    total_weight = sum(included_default_weights.values())

    if total_weight == 0:
        equal_weight = 1 / len(included_default_weights)
        return {model_name: equal_weight for model_name in included_default_weights}

    return {
        model_name: weight / total_weight
        for model_name, weight in included_default_weights.items()
    }


def filter_to_best_backtests(df, best_backtests):
    keep_pairs = set(zip(best_backtests["model_name"], best_backtests["backtest_name"]))

    return df[
        df.apply(lambda r: (r["model_name"], r["backtest_name"]) in keep_pairs, axis=1)
    ].copy()


def build_long_horizon_backtest(df, model_weights):
    """
    Converts wide backtest rows into long format.

    One row per:
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

        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            print(f"Skipping {horizon}d because missing columns: {missing_cols}")
            continue

        temp = df[required_cols].copy()

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

        temp["model_buy_vote"] = (temp["return_pct_pred"] > BUY_RETURN_THRESHOLD).astype(int)
        temp["model_weight"] = temp["model_name"].map(model_weights).fillna(0.0)
        temp["weighted_buy_vote"] = temp["model_buy_vote"] * temp["model_weight"]
        temp["weighted_return_pct_pred"] = temp["return_pct_pred"] * temp["model_weight"]

        long_rows.append(temp)

    if not long_rows:
        return pd.DataFrame()

    long_df = pd.concat(long_rows, ignore_index=True)

    return long_df.dropna(
        subset=[
            "return_pct_pred",
            "return_pct_actual",
            "loss_probability",
            "model_weight",
        ]
    )


def create_weighted_vote_ensemble(long_df):
    """
    Creates weighted-vote ensemble by symbol/date/horizon.

    BUY when:
        weighted_buy_score >= WEIGHTED_BUY_SCORE_THRESHOLD

    This is a model agreement filter, not a pure prediction averaging ensemble.
    """

    group_cols = ["symbol", "test_start_date", "horizon"]

    ensemble = (
        long_df.groupby(group_cols)
        .agg(
            model_count=("model_name", "nunique"),
            models_used=("model_name", lambda x: ",".join(sorted(set(x)))),
            backtests_used=("backtest_name", lambda x: ",".join(sorted(set(x)))),
            previous_trading_date=("previous_trading_date", "first"),
            previous_close_before_test_start=("previous_close_before_test_start", "first"),
            test_end_date=("test_end_date", "max"),
            ensemble_return_pct_pred=("return_pct_pred", "mean"),
            weighted_pred_num=("weighted_return_pct_pred", "sum"),
            weighted_pred_den=("model_weight", "sum"),
            ensemble_return_pct_actual=("return_pct_actual", "first"),
            ensemble_close_actual=("close_actual", "first"),
            ensemble_loss_probability=("loss_probability", "mean"),
            positive_model_votes=("model_buy_vote", "sum"),
            total_model_weight=("model_weight", "sum"),
            weighted_buy_vote=("weighted_buy_vote", "sum"),
        )
        .reset_index()
    )

    ensemble = ensemble[ensemble["model_count"] >= MIN_MODELS_REQUIRED].copy()

    ensemble["ensemble_weighted_return_pct_pred"] = ensemble.apply(
        lambda r: safe_divide(r["weighted_pred_num"], r["weighted_pred_den"]),
        axis=1,
    )

    ensemble["ensemble_confidence_no_loss"] = 1 - ensemble["ensemble_loss_probability"]

    ensemble["weighted_buy_score"] = ensemble.apply(
        lambda r: safe_divide(r["weighted_buy_vote"], r["total_model_weight"]),
        axis=1,
    )

    ensemble["unweighted_buy_score"] = ensemble.apply(
        lambda r: safe_divide(r["positive_model_votes"], r["model_count"]),
        axis=1,
    )

    ensemble["ensemble_count_pred_positive"] = (
        ensemble["weighted_buy_score"] >= WEIGHTED_BUY_SCORE_THRESHOLD
    ).astype(int)

    ensemble["ensemble_signal"] = np.where(
        ensemble["ensemble_count_pred_positive"] == 1,
        "BUY",
        "NO_BUY",
    )

    ensemble["ensemble_count_pred_positive_w_actual_positive"] = (
        (ensemble["ensemble_count_pred_positive"] == 1)
        & (ensemble["ensemble_return_pct_actual"] > 0)
    ).astype(int)

    ensemble["ensemble_buy_profit_pct"] = ensemble.apply(
        lambda r: safe_divide(
            r["ensemble_count_pred_positive_w_actual_positive"],
            r["ensemble_count_pred_positive"],
        ),
        axis=1,
    )

    # Same success metrics as individual model level, recalculated from ensemble BUY signal.

    ensemble["ensemble_return_pct_model_on_numerator"] = np.where(
        ensemble["ensemble_count_pred_positive"] == 1,
        ensemble["ensemble_return_pct_actual"],
        0.0,
    )
    ensemble["ensemble_return_pct_model_on_denominator"] = (
        ensemble["ensemble_count_pred_positive"]
    )
    ensemble["ensemble_return_pct_model_on"] = ensemble.apply(
        lambda r: safe_divide(
            r["ensemble_return_pct_model_on_numerator"],
            r["ensemble_return_pct_model_on_denominator"],
        ),
        axis=1,
    )

    ensemble["ensemble_return_pct_model_off_numerator"] = (
        ensemble["ensemble_return_pct_actual"]
    )
    ensemble["ensemble_return_pct_model_off_denominator"] = 1
    ensemble["ensemble_return_pct_model_off"] = ensemble[
        "ensemble_return_pct_actual"
    ]

    ensemble["ensemble_return_pct_model_uplift"] = (
        ensemble["ensemble_return_pct_model_on"]
        - ensemble["ensemble_return_pct_model_off"]
    )

    ensemble["ensemble_profitable_model_on_numerator"] = (
        ensemble["ensemble_count_pred_positive_w_actual_positive"]
    )
    ensemble["ensemble_profitable_model_on_denominator"] = (
        ensemble["ensemble_count_pred_positive"]
    )
    ensemble["ensemble_profitable_model_on"] = ensemble.apply(
        lambda r: safe_divide(
            r["ensemble_profitable_model_on_numerator"],
            r["ensemble_profitable_model_on_denominator"],
        ),
        axis=1,
    )

    ensemble["ensemble_profitable_model_off_numerator"] = (
        ensemble["ensemble_return_pct_actual"] > 0
    ).astype(int)
    ensemble["ensemble_profitable_model_off_denominator"] = 1
    ensemble["ensemble_profitable_model_off"] = ensemble[
        "ensemble_profitable_model_off_numerator"
    ]

    ensemble["ensemble_profitable_model_uplift"] = (
        ensemble["ensemble_profitable_model_on"]
        - ensemble["ensemble_profitable_model_off"]
    )

    ensemble["ensemble_model_on_trade_count"] = ensemble["ensemble_count_pred_positive"]
    ensemble["ensemble_model_on_trade_rate"] = ensemble["ensemble_count_pred_positive"]
    ensemble["ensemble_model_on_total_return"] = np.where(
        ensemble["ensemble_count_pred_positive"] == 1,
        ensemble["ensemble_return_pct_actual"],
        0.0,
    )
    ensemble["ensemble_model_on_worst_return"] = np.where(
        ensemble["ensemble_count_pred_positive"] == 1,
        ensemble["ensemble_return_pct_actual"],
        np.nan,
    )

    ensemble["buy_return_threshold"] = BUY_RETURN_THRESHOLD
    ensemble["weighted_buy_score_threshold"] = WEIGHTED_BUY_SCORE_THRESHOLD

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
            avg_weighted_pred_return=("ensemble_weighted_return_pct_pred", "mean"),
            avg_actual_return=("ensemble_return_pct_actual", "mean"),
            avg_weighted_buy_score=("weighted_buy_score", "mean"),
            avg_unweighted_buy_score=("unweighted_buy_score", "mean"),
            sum_count_pred_positive=("ensemble_count_pred_positive", "sum"),
            sum_count_pred_positive_w_actual_positive=(
                "ensemble_count_pred_positive_w_actual_positive",
                "sum",
            ),
            avg_loss_probability=("ensemble_loss_probability", "mean"),
            return_model_on_num=("ensemble_return_pct_model_on_numerator", "sum"),
            return_model_on_den=("ensemble_return_pct_model_on_denominator", "sum"),
            return_model_off_num=("ensemble_return_pct_model_off_numerator", "sum"),
            return_model_off_den=("ensemble_return_pct_model_off_denominator", "sum"),
            profitable_model_on_num=("ensemble_profitable_model_on_numerator", "sum"),
            profitable_model_on_den=("ensemble_profitable_model_on_denominator", "sum"),
            profitable_model_off_num=("ensemble_profitable_model_off_numerator", "sum"),
            profitable_model_off_den=("ensemble_profitable_model_off_denominator", "sum"),
            model_on_total_return=("ensemble_model_on_total_return", "sum"),
            model_on_worst_return=("ensemble_model_on_worst_return", "min"),
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

    summary["return_pct_model_on"] = summary.apply(
        lambda r: safe_divide(r["return_model_on_num"], r["return_model_on_den"]),
        axis=1,
    )
    summary["return_pct_model_off"] = summary.apply(
        lambda r: safe_divide(r["return_model_off_num"], r["return_model_off_den"]),
        axis=1,
    )
    summary["return_pct_model_uplift"] = (
        summary["return_pct_model_on"] - summary["return_pct_model_off"]
    )

    summary["profitable_model_on"] = summary.apply(
        lambda r: safe_divide(
            r["profitable_model_on_num"],
            r["profitable_model_on_den"],
        ),
        axis=1,
    )
    summary["profitable_model_off"] = summary.apply(
        lambda r: safe_divide(
            r["profitable_model_off_num"],
            r["profitable_model_off_den"],
        ),
        axis=1,
    )
    summary["profitable_model_uplift"] = (
        summary["profitable_model_on"] - summary["profitable_model_off"]
    )

    summary["model_on_trade_rate"] = summary.apply(
        lambda r: safe_divide(r["sum_count_pred_positive"], r["rows"]),
        axis=1,
    )

    return summary.sort_values(["symbol", "horizon"]).reset_index(drop=True)


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

    model_weights = build_model_weights(best_backtests)

    print("\nModel weights:")
    for model_name, weight in sorted(model_weights.items()):
        print(f"{model_name}: {weight:.4f}")

    df_best = filter_to_best_backtests(df, best_backtests)

    print(f"\nRows after filtering to best backtests: {len(df_best):,}")

    long_df = build_long_horizon_backtest(df_best, model_weights)

    print(f"Long-format rows: {len(long_df):,}")

    ensemble = create_weighted_vote_ensemble(long_df)

    print(f"Ensemble rows: {len(ensemble):,}")

    ensemble.to_csv(ENSEMBLE_BACKTEST_OUTPUT_PATH, index=False)

    print(f"\nSaved ensemble backtest to: {ENSEMBLE_BACKTEST_OUTPUT_PATH}")

    summary = summarise_ensemble(ensemble)

    print("\nEnsemble summary:")
    print(summary)


if __name__ == "__main__":
    main()
