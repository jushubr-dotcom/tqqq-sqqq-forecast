import os
import numpy as np
import pandas as pd


# ============================================================
# CONFIG
# ============================================================

OUTPUT_DIR = "outputs"

PRODUCTION_INPUT_PATH = os.path.join(OUTPUT_DIR, "production_forecast.csv")
ENSEMBLE_PRODUCTION_OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "ensemble_production_forecast.csv",
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
BUY_RETURN_THRESHOLD = float(os.getenv("BUY_RETURN_THRESHOLD", "0.0"))


# ============================================================
# HELPERS
# ============================================================

def build_long_production(df):
    long_rows = []

    for horizon in HORIZONS:
        pred_col = f"{horizon}d_return_pct_pred"
        close_pred_col = f"{horizon}d_close_pred"
        conf_col = f"{horizon}d_confidence_no_loss"
        loss_col = f"{horizon}d_loss_probability"

        required_cols = [
            "forecast_date",
            "model_name",
            "production_model_name",
            "data_as_of_date",
            "stock_symbol",
            "stock_end_value",
            pred_col,
            close_pred_col,
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
                "stock_symbol": "symbol",
                "stock_end_value": "base_close",
                pred_col: "return_pct_pred",
                close_pred_col: "close_pred",
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
            "close_pred",
            "loss_probability",
        ]
    )

    return long_df


def create_production_ensemble(long_df):
    """
    Creates one ensemble prediction per:
        forecast_date
        data_as_of_date
        symbol
        horizon

    If production_forecast.csv has multiple historical runs, this uses only
    the latest forecast_date.
    """

    long_df = long_df.copy()

    long_df["forecast_date"] = pd.to_datetime(long_df["forecast_date"])
    long_df["data_as_of_date"] = pd.to_datetime(long_df["data_as_of_date"])

    latest_forecast_date = long_df["forecast_date"].max()

    latest = long_df[long_df["forecast_date"] == latest_forecast_date].copy()

    group_cols = [
        "forecast_date",
        "data_as_of_date",
        "symbol",
        "horizon",
    ]

    ensemble = (
        latest.groupby(group_cols)
        .agg(
            model_count=("model_name", "nunique"),
            models_used=("model_name", lambda x: ",".join(sorted(set(x)))),
            production_models_used=(
                "production_model_name",
                lambda x: ",".join(sorted(set(x))),
            ),
            base_close=("base_close", "first"),
            ensemble_return_pct_pred=("return_pct_pred", "mean"),
            ensemble_close_pred=("close_pred", "mean"),
            ensemble_confidence_no_loss=("confidence_no_loss", "mean"),
            ensemble_loss_probability=("loss_probability", "mean"),
            min_return_pct_pred=("return_pct_pred", "min"),
            max_return_pct_pred=("return_pct_pred", "max"),
            median_return_pct_pred=("return_pct_pred", "median"),
            model_votes_positive=(
                "return_pct_pred",
                lambda x: int((x > BUY_RETURN_THRESHOLD).sum()),
            ),
        )
        .reset_index()
    )

    ensemble = ensemble[ensemble["model_count"] >= MIN_MODELS_REQUIRED].copy()

    ensemble["model_vote_positive_pct"] = (
        ensemble["model_votes_positive"] / ensemble["model_count"]
    )

    ensemble["ensemble_pred_positive"] = (
        ensemble["ensemble_return_pct_pred"] > BUY_RETURN_THRESHOLD
    ).astype(int)

    ensemble["ensemble_signal"] = np.where(
        ensemble["ensemble_return_pct_pred"] > BUY_RETURN_THRESHOLD,
        "BUY",
        "NO_BUY",
    )

    ensemble["buy_return_threshold"] = BUY_RETURN_THRESHOLD
    ensemble["min_models_required"] = MIN_MODELS_REQUIRED

    ensemble = ensemble.sort_values(
        ["symbol", "horizon"]
    ).reset_index(drop=True)

    return ensemble


# ============================================================
# MAIN
# ============================================================

def main():
    if not os.path.exists(PRODUCTION_INPUT_PATH):
        raise FileNotFoundError(f"Missing input file: {PRODUCTION_INPUT_PATH}")

    df = pd.read_csv(PRODUCTION_INPUT_PATH, low_memory=False)

    df = df[df["model_name"].isin(MODEL_NAMES_TO_INCLUDE)].copy()

    if df.empty:
        raise ValueError("No rows found for selected model names.")

    long_df = build_long_production(df)

    print(f"Long-format production rows: {len(long_df):,}")

    if long_df.empty:
        raise ValueError("No valid long-format production rows were created.")

    ensemble = create_production_ensemble(long_df)

    print("\nProduction ensemble:")
    print(ensemble)

    ensemble.to_csv(ENSEMBLE_PRODUCTION_OUTPUT_PATH, index=False)

    print(f"\nSaved production ensemble to: {ENSEMBLE_PRODUCTION_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
