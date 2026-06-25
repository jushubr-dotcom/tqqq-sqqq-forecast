import os
import re
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import ExtraTreesRegressor, ExtraTreesClassifier
from sklearn.metrics import mean_absolute_error, mean_squared_error
from backtest_metrics import (
    add_horizon_success_metrics,
    add_average_success_metrics,
    get_success_metric_columns,
)


warnings.filterwarnings("ignore")


# ============================================================
# CONFIG
# ============================================================

RUN_TIMESTAMP = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

SYMBOLS = ["TQQQ", "SQQQ"]

HORIZONS = [3, 5, 7, 9]

LAG_DAYS = list(range(1, 53))

RETURN_WINDOWS = [5, 7, 10, 14, 20]

# Backtest window is controlled from YAML in months.
# Example: BACKTEST_DURATION_MONTHS=8 and BACKTEST_END_DATE=2026-05-31
# tests the final 8 months ending on 2026-05-31.
BACKTEST_END_DATE = os.getenv("BACKTEST_END_DATE", "2026-05-31")
BACKTEST_DURATION_MONTHS = int(os.getenv("BACKTEST_DURATION_MONTHS", "8"))
BACKTEST_START_DATE = (
    pd.to_datetime(BACKTEST_END_DATE) - pd.DateOffset(months=BACKTEST_DURATION_MONTHS)
).strftime("%Y-%m-%d")

OUTPUT_DIR = "outputs"
BACKTEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "backtest_results.csv")
PRODUCTION_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "production_forecast.csv")
FEATURE_IMPORTANCE_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "feature_importance_results.csv")
FEATURE_IMPORTANCE_SUMMARY_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "feature_importance_summary.csv")

SMOKE_TEST = os.getenv("SMOKE_TEST", "false").lower() == "true"
SMOKE_TEST_DAYS_PER_SYMBOL = int(os.getenv("SMOKE_TEST_DAYS_PER_SYMBOL", "10"))
SMOKE_TEST_PARAMETER_COUNT = int(os.getenv("SMOKE_TEST_PARAMETER_COUNT", "2"))

MODEL_NAME = os.getenv("MODEL_NAME", "ExtraTrees")

# ============================================================
# FEATURE IMPORTANCE / AUDIT CONFIG
# ============================================================
# Logs native tree feature importances for every trained return model and loss model.
# This gives you a standardized audit trail by run, model, backtest, symbol, date, and horizon.
LOG_FEATURE_IMPORTANCE = os.getenv("LOG_FEATURE_IMPORTANCE", "true").lower() == "true"
FEATURE_IMPORTANCE_TOP_N = int(os.getenv("FEATURE_IMPORTANCE_TOP_N", "50"))
LOG_LOSS_MODEL_IMPORTANCE = os.getenv("LOG_LOSS_MODEL_IMPORTANCE", "true").lower() == "true"

# ============================================================
# FEATURE SET CONFIG
# ============================================================
# Default true because raw ETF price levels and raw close lags are not stationary.
# If you want to compare with the old feature set, set:
#   EXCLUDE_RAW_PRICE_LEVEL_FEATURES=false
EXCLUDE_RAW_PRICE_LEVEL_FEATURES = (
    os.getenv("EXCLUDE_RAW_PRICE_LEVEL_FEATURES", "true").lower() == "true"
)

# Generic feature selection framework.
#
# FEATURE_SELECTION_MODE controls which engineered features are allowed into the model:
#   all     = use all numeric engineered features, after optional raw price-level removal
#   include = use only features matching INCLUDE_FEATURE_NAMES / INCLUDE_FEATURE_PREFIXES
#   exclude = use all eligible features except those matching EXCLUDE_FEATURE_NAMES / EXCLUDE_FEATURE_PREFIXES
#
# This lets you start with a small, intentional subset and add feature groups incrementally
# without editing the Python code each time.
FEATURE_SELECTION_MODE = os.getenv("FEATURE_SELECTION_MODE", "all").strip().lower()

if FEATURE_SELECTION_MODE not in {"all", "include", "exclude"}:
    raise ValueError(
        "FEATURE_SELECTION_MODE must be one of: all, include, exclude. "
        f"Received: {FEATURE_SELECTION_MODE}"
    )

def parse_csv_env_var(env_name):
    return [
        x.strip()
        for x in os.getenv(env_name, "").split(",")
        if x.strip()
    ]

INCLUDE_FEATURE_NAMES = parse_csv_env_var("INCLUDE_FEATURE_NAMES")
INCLUDE_FEATURE_PREFIXES = parse_csv_env_var("INCLUDE_FEATURE_PREFIXES")
EXCLUDE_FEATURE_NAMES = parse_csv_env_var("EXCLUDE_FEATURE_NAMES")
EXCLUDE_FEATURE_PREFIXES = parse_csv_env_var("EXCLUDE_FEATURE_PREFIXES")

# This label is appended to the feature-set part of backtest_name so outputs clearly show what was tested.
# Examples: core_reversal, core_reversal_candle, no_streak, all_features
FEATURE_TEST_LABEL = os.getenv("FEATURE_TEST_LABEL", "").strip()

# Additional free-text suffix from YAML, appended after duration + feature-set suffix.
# Use this for experiment labels like v2, no_bad_features, candle_addon, etc.
ADDITIONAL_BACKTEST_SUFFIX = os.getenv("ADDITIONAL_BACKTEST_SUFFIX", "").strip()

MA_WINDOWS = [3, 5, 7, 14, 20, 28, 52]
ROLLING_EXTREME_WINDOWS = [3, 5, 10, 20, 52]
VOLATILITY_WINDOWS = [3, 5, 10, 20]
STREAK_WINDOWS = [3, 5, 10]
OTHER_SYMBOL_RETURN_WINDOWS = [2, 3, 5, 10]

# ============================================================
# MARKET REGIME FILTER CONFIG
# ============================================================
# Easy off switch:
#   USE_MARKET_REGIME_FILTER=false
#
# Loose defaults first, so the filter does not kill BUY count too aggressively.
# These are evaluated using the previous trading row only, so they are leak-safe.
USE_MARKET_REGIME_FILTER = os.getenv("USE_MARKET_REGIME_FILTER", "true").lower() == "true"
REGIME_MIN_MA_RATIO_28 = float(os.getenv("REGIME_MIN_MA_RATIO_28", "0.98"))
REGIME_MIN_RETURN_20D = float(os.getenv("REGIME_MIN_RETURN_20D", "-0.08"))
REGIME_MAX_HIGH_LOW_RANGE = float(os.getenv("REGIME_MAX_HIGH_LOW_RANGE", "0.12"))



# ============================================================
# EXTRA TREES PARAMETER GRID
# ============================================================

PARAMETER_GRID = [
    # 75 trees: check if fewer trees generalise better
    {
        "backtest_name": "et_75trees_depth4_leaf20_sqrt_8m",
        "n_estimators": 75,
        "max_depth": 4,
        "min_samples_leaf": 20,
        "max_features": "sqrt",
        "random_state": 42,
    },
]

PRODUCTION_MODEL_PARAMS = PARAMETER_GRID[-1]


# ============================================================
# HELPERS
# ============================================================

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def append_row_to_csv(row, output_path):
    """
    Appends one row to CSV while preserving historical rows.

    If the existing CSV is missing new columns, this function rewrites the file
    with the expanded schema and keeps all previous rows.
    """

    row_df = pd.DataFrame([row])

    if not os.path.exists(output_path):
        row_df.to_csv(output_path, mode="w", header=True, index=False)
        return

    existing_df = pd.read_csv(output_path)

    all_columns = list(existing_df.columns)

    for col in row_df.columns:
        if col not in all_columns:
            all_columns.append(col)

    for col in all_columns:
        if col not in existing_df.columns:
            existing_df[col] = np.nan

        if col not in row_df.columns:
            row_df[col] = np.nan

    existing_df = existing_df[all_columns]
    row_df = row_df[all_columns]

    combined_df = pd.concat([existing_df, row_df], ignore_index=True)

    combined_df.to_csv(output_path, mode="w", header=True, index=False)
    
def safe_divide(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def feature_matches_any_rule(feature_name, exact_names, prefixes):
    """Returns True when a feature matches any exact-name or prefix rule."""

    if feature_name in exact_names:
        return True

    return any(
        feature_name.startswith(prefix)
        for prefix in prefixes
    )


def is_custom_included_feature(feature_name):
    """Returns True when a feature is allowed by the YAML-controlled include list."""

    return feature_matches_any_rule(
        feature_name=feature_name,
        exact_names=INCLUDE_FEATURE_NAMES,
        prefixes=INCLUDE_FEATURE_PREFIXES,
    )


def is_custom_excluded_feature(feature_name):
    """Returns True when a feature is blocked by the YAML-controlled exclude list."""

    return feature_matches_any_rule(
        feature_name=feature_name,
        exact_names=EXCLUDE_FEATURE_NAMES,
        prefixes=EXCLUDE_FEATURE_PREFIXES,
    )


def sanitize_name_part(value):
    """Returns a safe compact label for backtest names and pivot tables."""

    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def get_backtest_duration_suffix():
    """Documents the YAML-controlled backtest duration in months."""

    return f"bt{BACKTEST_DURATION_MONTHS}m"


def get_feature_set_suffix():
    """Builds a compact suffix that documents the active feature set."""

    suffixes = []

    if EXCLUDE_RAW_PRICE_LEVEL_FEATURES:
        suffixes.append("no_rawpx")
    else:
        suffixes.append("rawpx_on")

    feature_label = sanitize_name_part(FEATURE_TEST_LABEL)

    if feature_label:
        suffixes.append(feature_label)
    else:
        suffixes.append(FEATURE_SELECTION_MODE)

    return "_".join(suffixes)


def get_additional_backtest_suffix():
    """Returns optional YAML free-text experiment suffix."""

    return sanitize_name_part(ADDITIONAL_BACKTEST_SUFFIX)


def get_effective_backtest_name(base_backtest_name):
    """Adds duration, feature-set and optional YAML suffix to the base hyperparameter name."""

    parts = [
        base_backtest_name,
        get_backtest_duration_suffix(),
        f"fs_{get_feature_set_suffix()}",
    ]

    additional_suffix = get_additional_backtest_suffix()

    if additional_suffix:
        parts.append(additional_suffix)

    return "__".join(parts)


def is_raw_price_level_feature(feature_name):
    """Returns True for raw price/level features that are usually non-stationary."""

    if feature_name in {"open", "high", "low", "close", "volume", "other_symbol_close"}:
        return True

    if feature_name.startswith("close_lag_") and not feature_name.endswith("_ratio"):
        return True

    if feature_name.startswith("ma_") and not (
        feature_name.startswith("ma_ratio_") or feature_name.startswith("ma_slope_")
    ):
        return True

    if feature_name.startswith("rolling_high_") or feature_name.startswith("rolling_low_"):
        return True

    if feature_name.startswith("volume_ma_"):
        return True

    return False


def get_feature_config_string(values):
    """Stores feature-selection config as a stable semicolon-separated string for CSV outputs."""

    if not values:
        return ""

    return ";".join(values)


def get_native_importance_array(model):
    """
    Returns a native importance array when the model exposes feature_importances_.
    Works for ExtraTrees, RandomForest, XGBoost sklearn wrapper, LightGBM sklearn wrapper,
    and CatBoost when wrapped similarly. Returns None if unavailable.
    """

    if model is None or not hasattr(model, "feature_importances_"):
        return None

    importances = np.asarray(model.feature_importances_, dtype=float)

    if importances.size == 0:
        return None

    return importances


def build_feature_importance_rows(
    model,
    feature_cols,
    run_timestamp,
    model_name,
    backtest_name,
    symbol,
    test_start_date,
    prediction_input_date,
    horizon,
    model_component,
    return_pct_pred=None,
    return_pct_actual=None,
    confidence_no_loss=None,
    loss_probability=None,
    raw_pred_positive=None,
    regime_filtered_buy=None,
    top_n=FEATURE_IMPORTANCE_TOP_N,
):
    """
    Builds standardized native feature-importance rows for one fitted model.

    Each row is one feature for one trained model instance.
    The output is intentionally long-form so it can be pivoted by model/backtest/horizon/feature.
    """

    if not LOG_FEATURE_IMPORTANCE:
        return []

    importances = get_native_importance_array(model)

    if importances is None:
        return []

    if len(importances) != len(feature_cols):
        print(
            f"Feature-importance length mismatch for {backtest_name} | {symbol} | "
            f"horizon={horizon} | component={model_component}: "
            f"{len(importances)} importances vs {len(feature_cols)} features.",
            flush=True,
        )
        return []

    total_importance = float(np.nansum(importances))
    ranked_indices = np.argsort(importances)[::-1]

    if top_n is not None and top_n > 0:
        ranked_indices = ranked_indices[:top_n]

    rows = []

    for rank, idx in enumerate(ranked_indices, start=1):
        raw_importance = float(importances[idx])
        normalized_importance = safe_divide(raw_importance, total_importance)

        rows.append(
            {
                "run_timestamp": run_timestamp,
                "model_name": model_name,
                "backtest_name": backtest_name,
                "symbol": symbol,
                "test_start_date": test_start_date,
                "prediction_input_date": prediction_input_date,
                "horizon": horizon,
                "model_component": model_component,
                "importance_type": "native_tree_importance",
                "feature_name": feature_cols[idx],
                "rank": rank,
                "raw_importance": raw_importance,
                "normalized_importance": normalized_importance,
                "return_pct_pred": return_pct_pred,
                "return_pct_actual": return_pct_actual,
                "confidence_no_loss": confidence_no_loss,
                "loss_probability": loss_probability,
                "raw_pred_positive": int(raw_pred_positive) if raw_pred_positive is not None else np.nan,
                "regime_filtered_buy": int(regime_filtered_buy) if regime_filtered_buy is not None else np.nan,
            }
        )

    return rows


def append_rows_to_csv(rows, output_path):
    """Appends multiple rows to CSV using the same schema-expansion logic as append_row_to_csv."""

    if not rows:
        return

    rows_df = pd.DataFrame(rows)

    if rows_df.empty:
        return

    if not os.path.exists(output_path):
        rows_df.to_csv(output_path, mode="w", header=True, index=False)
        return

    existing_df = pd.read_csv(output_path)
    all_columns = list(existing_df.columns)

    for col in rows_df.columns:
        if col not in all_columns:
            all_columns.append(col)

    for col in all_columns:
        if col not in existing_df.columns:
            existing_df[col] = np.nan
        if col not in rows_df.columns:
            rows_df[col] = np.nan

    combined_df = pd.concat(
        [existing_df[all_columns], rows_df[all_columns]],
        ignore_index=True,
    )
    combined_df.to_csv(output_path, mode="w", header=True, index=False)


def build_feature_importance_summary(importance_rows):
    """
    Summarizes feature importance rows for one backtest parameter combination.
    This is the file to use for quick model-level feature audits.
    """

    if not importance_rows:
        return pd.DataFrame()

    df = pd.DataFrame(importance_rows)

    if df.empty:
        return pd.DataFrame()

    group_cols = [
        "run_timestamp",
        "model_name",
        "backtest_name",
        "symbol",
        "horizon",
        "model_component",
        "importance_type",
        "feature_name",
    ]

    summary = (
        df.groupby(group_cols, dropna=False)
        .agg(
            avg_raw_importance=("raw_importance", "mean"),
            median_raw_importance=("raw_importance", "median"),
            max_raw_importance=("raw_importance", "max"),
            avg_normalized_importance=("normalized_importance", "mean"),
            median_normalized_importance=("normalized_importance", "median"),
            max_normalized_importance=("normalized_importance", "max"),
            avg_rank=("rank", "mean"),
            best_rank=("rank", "min"),
            times_ranked=("rank", "count"),
            times_top_5=("rank", lambda x: int((x <= 5).sum())),
            times_top_10=("rank", lambda x: int((x <= 10).sum())),
            avg_return_pct_pred_when_ranked=("return_pct_pred", "mean"),
            avg_return_pct_actual_when_ranked=("return_pct_actual", "mean"),
            avg_loss_probability_when_ranked=("loss_probability", "mean"),
            buy_signal_count_when_ranked=("regime_filtered_buy", "sum"),
        )
        .reset_index()
    )

    summary = summary.sort_values(
        [
            "run_timestamp",
            "model_name",
            "backtest_name",
            "symbol",
            "horizon",
            "model_component",
            "avg_normalized_importance",
        ],
        ascending=[True, True, True, True, True, True, False],
    ).reset_index(drop=True)

    return summary


def write_feature_importance_outputs(importance_rows):
    """Writes detailed feature importance rows and a summarized feature audit."""

    if not LOG_FEATURE_IMPORTANCE or not importance_rows:
        return

    append_rows_to_csv(importance_rows, FEATURE_IMPORTANCE_OUTPUT_PATH)

    summary_df = build_feature_importance_summary(importance_rows)

    if not summary_df.empty:
        append_rows_to_csv(
            summary_df.to_dict(orient="records"),
            FEATURE_IMPORTANCE_SUMMARY_OUTPUT_PATH,
        )

    print(
        f"Feature importance rows written: {len(importance_rows):,} | "
        f"detail={FEATURE_IMPORTANCE_OUTPUT_PATH} | "
        f"summary={FEATURE_IMPORTANCE_SUMMARY_OUTPUT_PATH}",
        flush=True,
    )


def get_market_regime_flags(row):
    """
    Returns leak-safe market-regime diagnostics using only the prediction input row.

    In backtest, row must be previous_row, not the current test-day row.
    In production, row is latest_row.
    """

    ma_ratio_28 = float(row.iloc[0].get("ma_ratio_28", np.nan))
    return_20d_past = float(row.iloc[0].get("return_20d_past", np.nan))
    high_low_range = float(row.iloc[0].get("high_low_range", np.nan))

    trend_ok = not pd.isna(ma_ratio_28) and ma_ratio_28 >= REGIME_MIN_MA_RATIO_28
    momentum_ok = not pd.isna(return_20d_past) and return_20d_past >= REGIME_MIN_RETURN_20D
    volatility_ok = not pd.isna(high_low_range) and high_low_range <= REGIME_MAX_HIGH_LOW_RANGE

    regime_ok = trend_ok and momentum_ok and volatility_ok

    return {
        "regime_filter_enabled": bool(USE_MARKET_REGIME_FILTER),
        "regime_ok": bool(regime_ok),
        "regime_trend_ok": bool(trend_ok),
        "regime_momentum_ok": bool(momentum_ok),
        "regime_volatility_ok": bool(volatility_ok),
        "regime_ma_ratio_28": ma_ratio_28,
        "regime_return_20d_past": return_20d_past,
        "regime_high_low_range": high_low_range,
        "regime_min_ma_ratio_28_threshold": REGIME_MIN_MA_RATIO_28,
        "regime_min_return_20d_threshold": REGIME_MIN_RETURN_20D,
        "regime_max_high_low_range_threshold": REGIME_MAX_HIGH_LOW_RANGE,
    }


def apply_market_regime_filter(raw_pred_positive, regime_flags):
    """
    Applies the optional market-regime gate to a raw positive prediction.

    If USE_MARKET_REGIME_FILTER=false, this returns raw_pred_positive unchanged.
    """

    if USE_MARKET_REGIME_FILTER:
        return bool(raw_pred_positive and regime_flags["regime_ok"])

    return bool(raw_pred_positive)


def get_top_features_from_importances(feature_cols, importance_arrays, top_n=5):
    if not importance_arrays:
        return [None] * top_n

    importance_matrix = np.vstack(importance_arrays)
    avg_importance = importance_matrix.mean(axis=0)

    ranked_indices = np.argsort(avg_importance)[::-1]
    top_features = [feature_cols[i] for i in ranked_indices[:top_n]]

    while len(top_features) < top_n:
        top_features.append(None)

    return top_features


# ============================================================
# DATA DOWNLOAD + CLEANING
# ============================================================

def download_one_symbol(symbol, max_retries=3):
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(
                f"Downloading {symbol} from Yahoo Finance... "
                f"attempt {attempt}/{max_retries}",
                flush=True,
            )

            df = yf.download(
                tickers=symbol,
                period="5y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )

            if df is None or df.empty:
                raise ValueError(f"No data returned for {symbol}")

            df = df.reset_index()

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [
                    col[0].lower().replace(" ", "_")
                    if isinstance(col, tuple)
                    else str(col).lower().replace(" ", "_")
                    for col in df.columns
                ]
            else:
                df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

            df["symbol"] = symbol

            expected_cols = ["date", "open", "high", "low", "close", "volume", "symbol"]
            missing_cols = [col for col in expected_cols if col not in df.columns]

            if missing_cols:
                raise ValueError(
                    f"Missing columns for {symbol}: {missing_cols}. "
                    f"Available columns: {list(df.columns)}"
                )

            df = df[expected_cols]

            print(f"Downloaded {symbol}: {len(df):,} rows.", flush=True)

            return df

        except Exception as e:
            last_error = e
            print(
                f"Download failed for {symbol} on attempt {attempt}: {e}",
                flush=True,
            )

    raise RuntimeError(
        f"Failed to download {symbol} after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


def download_data(symbols):
    print("Downloading data from Yahoo Finance...", flush=True)

    frames = []

    for symbol in symbols:
        symbol_df = download_one_symbol(symbol)
        frames.append(symbol_df)

    data = pd.concat(frames, ignore_index=True)

    data["date"] = pd.to_datetime(data["date"]).dt.date
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    downloaded_symbols = sorted(data["symbol"].unique().tolist())
    missing_symbols = sorted(set(symbols) - set(downloaded_symbols))

    if missing_symbols:
        raise RuntimeError(
            f"Missing required symbols after download: {missing_symbols}. "
            f"Downloaded symbols: {downloaded_symbols}"
        )

    print(f"Downloaded total rows: {len(data):,}", flush=True)
    print(f"Downloaded symbols: {downloaded_symbols}", flush=True)

    return data


def clean_data(data):
    print("Cleaning data...", flush=True)

    data = data.copy()

    numeric_cols = ["open", "high", "low", "close", "volume"]

    for col in numeric_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna(subset=["date", "symbol", "open", "high", "low", "close"])
    data = data[data["open"] > 0]
    data = data[data["high"] > 0]
    data = data[data["low"] > 0]
    data = data[data["close"] > 0]
    data = data[data["volume"] >= 0]

    data = data.drop_duplicates(subset=["symbol", "date"])
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    print(f"Cleaned data has {len(data):,} rows.", flush=True)

    return data


def add_cross_symbol_features(data):
    print("Adding cross-symbol features...", flush=True)

    available_symbols = sorted(data["symbol"].unique().tolist())
    missing_symbols = sorted(set(SYMBOLS) - set(available_symbols))

    if missing_symbols:
        raise RuntimeError(
            f"Cannot create cross-symbol features. "
            f"Missing symbols: {missing_symbols}. "
            f"Available symbols: {available_symbols}"
        )

    wide_close = data.pivot(index="date", columns="symbol", values="close").reset_index()

    required_columns = ["date", "TQQQ", "SQQQ"]
    missing_columns = [col for col in required_columns if col not in wide_close.columns]

    if missing_columns:
        raise RuntimeError(
            f"Cross-symbol pivot is missing columns: {missing_columns}. "
            f"Available columns: {list(wide_close.columns)}"
        )

    tqqq_map = wide_close[["date", "TQQQ"]].rename(columns={"TQQQ": "tqqq_close"})
    sqqq_map = wide_close[["date", "SQQQ"]].rename(columns={"SQQQ": "sqqq_close"})

    data = data.merge(tqqq_map, on="date", how="left")
    data = data.merge(sqqq_map, on="date", how="left")

    data["other_symbol_close"] = np.where(
        data["symbol"] == "TQQQ",
        data["sqqq_close"],
        data["tqqq_close"],
    )

    data = data.drop(columns=["tqqq_close", "sqqq_close"])

    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    return data


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(data):
    print("Creating features...", flush=True)

    data = data.copy()
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    feature_frames = []

    for symbol in SYMBOLS:
        print(f"Creating features for {symbol}...", flush=True)

        df = data[data["symbol"] == symbol].copy()
        df = df.sort_values("date").reset_index(drop=True)

        # ------------------------------------------------------------
        # Basic daily behaviour
        # ------------------------------------------------------------
        df["daily_return"] = df["close"].pct_change()
        df["open_to_close_return"] = (df["close"] - df["open"]) / df["open"]
        df["high_low_range"] = (df["high"] - df["low"]) / df["close"]
        df["gap_return"] = (df["open"] / df["close"].shift(1)) - 1

        # Where did the close finish inside the daily candle?
        # 0 = close at low, 1 = close at high.
        daily_range = df["high"] - df["low"]

        df["close_location_in_range"] = np.where(
            daily_range != 0,
            (df["close"] - df["low"]) / daily_range,
            np.nan,
        )

        df["upper_wick_pct"] = np.where(
            daily_range != 0,
            (df["high"] - df[["open", "close"]].max(axis=1)) / daily_range,
            np.nan,
        )

        df["lower_wick_pct"] = np.where(
            daily_range != 0,
            (df[["open", "close"]].min(axis=1) - df["low"]) / daily_range,
            np.nan,
        )

        df["gap_filled_intraday"] = np.where(
            df["gap_return"] > 0,
            (df["low"] <= df["close"].shift(1)).astype(int),
            (df["high"] >= df["close"].shift(1)).astype(int),
        )

        # ------------------------------------------------------------
        # Lag features
        # ------------------------------------------------------------
        # Keep raw close lags for optional backwards compatibility,
        # but get_feature_columns() excludes them by default because raw price
        # levels are not stationary.
        # The ratio version is the preferred feature.
        for lag in LAG_DAYS:
            df[f"close_lag_{lag}"] = df["close"].shift(lag)
            df[f"close_lag_{lag}_ratio"] = (df["close"] / df["close"].shift(lag)) - 1
            df[f"return_lag_{lag}"] = df["daily_return"].shift(lag)

        # ------------------------------------------------------------
        # Moving averages, trend and recovery features
        # ------------------------------------------------------------
        for window in MA_WINDOWS:
            df[f"ma_{window}"] = df["close"].rolling(window=window).mean()
            df[f"ma_ratio_{window}"] = df["close"] / df[f"ma_{window}"]

            # Slope of the moving average over the last 3 trading days.
            df[f"ma_slope_{window}"] = (df[f"ma_{window}"] / df[f"ma_{window}"].shift(3)) - 1

            # Explicit binary trend state.
            df[f"close_above_ma_{window}"] = (
                df["close"] > df[f"ma_{window}"]
            ).astype(int)

        # Existing return windows plus very short-term 2d/3d recovery windows.
        return_windows = sorted(set(RETURN_WINDOWS + [2, 3]))

        for window in return_windows:
            df[f"return_{window}d_past"] = df["close"].pct_change(window)

        # ------------------------------------------------------------
        # Drawdown and rebound-from-low features
        # ------------------------------------------------------------
        # These are the key additions for the issue you observed:
        # after a selloff, old lag/trend features can still look bearish,
        # while rebound_from_low can tell the model that recovery has started.
        for window in ROLLING_EXTREME_WINDOWS:
            df[f"rolling_high_{window}"] = df["close"].rolling(window=window).max()
            df[f"rolling_low_{window}"] = df["close"].rolling(window=window).min()

            df[f"drawdown_from_high_{window}"] = (
                df["close"] / df[f"rolling_high_{window}"]
            ) - 1

            df[f"rebound_from_low_{window}"] = (
                df["close"] / df[f"rolling_low_{window}"]
            ) - 1

        # ------------------------------------------------------------
        # Rolling volatility / choppiness
        # ------------------------------------------------------------
        for window in VOLATILITY_WINDOWS:
            df[f"return_volatility_{window}d"] = (
                df["daily_return"].rolling(window=window).std()
            )

            df[f"avg_high_low_range_{window}d"] = (
                df["high_low_range"].rolling(window=window).mean()
            )

        # ------------------------------------------------------------
        # Up/down day streaks and rolling counts
        # ------------------------------------------------------------
        df["is_up_day"] = (df["daily_return"] > 0).astype(int)
        df["is_down_day"] = (df["daily_return"] < 0).astype(int)

        for window in STREAK_WINDOWS:
            df[f"up_days_{window}"] = df["is_up_day"].rolling(window=window).sum()
            df[f"down_days_{window}"] = df["is_down_day"].rolling(window=window).sum()

        up_groups = (df["is_up_day"] != df["is_up_day"].shift()).cumsum()
        down_groups = (df["is_down_day"] != df["is_down_day"].shift()).cumsum()

        df["consecutive_up_days"] = df["is_up_day"].groupby(up_groups).cumsum()
        df["consecutive_down_days"] = df["is_down_day"].groupby(down_groups).cumsum()

        # ------------------------------------------------------------
        # Volume features
        # ------------------------------------------------------------
        # Raw volume is excluded by default later; these normalized features are safer.
        df["volume_change_1d"] = df["volume"].pct_change()

        for window in [5, 10, 20]:
            df[f"volume_ma_{window}"] = df["volume"].rolling(window=window).mean()
            df[f"volume_ratio_{window}"] = df["volume"] / df[f"volume_ma_{window}"]

        # ------------------------------------------------------------
        # Cross-symbol features
        # ------------------------------------------------------------
        # For TQQQ rows, other_symbol is SQQQ.
        # For SQQQ rows, other_symbol is TQQQ.
        #
        # Use returns/spreads rather than raw other_symbol_close because inverse ETF
        # price levels decay over time and are affected by splits.
        df["other_symbol_return"] = df["other_symbol_close"].pct_change()

        for window in OTHER_SYMBOL_RETURN_WINDOWS:
            df[f"other_symbol_return_{window}d"] = (
                df["other_symbol_close"].pct_change(window)
            )

        df["inverse_pressure_1d"] = -df["other_symbol_return"]

        df["tqqq_vs_inverse_sqqq_return_gap"] = (
            df["daily_return"] - (-df["other_symbol_return"])
        )

        for window in [3, 5, 10]:
            df[f"inverse_pressure_{window}d"] = -df[f"other_symbol_return_{window}d"]
            df[f"return_vs_inverse_pressure_gap_{window}d"] = (
                df[f"return_{window}d_past"] - df[f"inverse_pressure_{window}d"]
            )

        # ------------------------------------------------------------
        # Targets
        # ------------------------------------------------------------
        for horizon in HORIZONS:
            df[f"actual_{horizon}d_close"] = df["close"].shift(-horizon)
            df[f"actual_{horizon}d_date"] = df["date"].shift(-horizon)

            df[f"target_return_{horizon}d"] = (
                df[f"actual_{horizon}d_close"] / df["close"]
            ) - 1

            df[f"target_loss_{horizon}d"] = np.where(
                df[f"target_return_{horizon}d"] < 0,
                1,
                0,
            )

        df = df.replace([np.inf, -np.inf], np.nan)

        feature_frames.append(df)

    features = pd.concat(feature_frames, ignore_index=True)
    features = features.sort_values(["symbol", "date"]).reset_index(drop=True)

    print(f"Feature dataset has {len(features):,} rows.", flush=True)

    return features


def get_feature_columns(df):
    excluded_cols = ["date", "symbol"]

    target_cols = []

    for horizon in HORIZONS:
        target_cols.append(f"actual_{horizon}d_close")
        target_cols.append(f"actual_{horizon}d_date")
        target_cols.append(f"target_return_{horizon}d")
        target_cols.append(f"target_loss_{horizon}d")

    excluded_cols += target_cols

    all_numeric_feature_cols = [
        col
        for col in df.columns
        if col not in excluded_cols
        and pd.api.types.is_numeric_dtype(df[col])
    ]

    feature_cols = []
    raw_price_excluded_count = 0

    for col in all_numeric_feature_cols:
        if EXCLUDE_RAW_PRICE_LEVEL_FEATURES and is_raw_price_level_feature(col):
            raw_price_excluded_count += 1
            continue

        feature_cols.append(col)

    before_selection_count = len(feature_cols)

    if FEATURE_SELECTION_MODE == "include":
        feature_cols = [
            col
            for col in feature_cols
            if is_custom_included_feature(col)
        ]
        selection_removed_count = before_selection_count - len(feature_cols)

        if not feature_cols:
            raise RuntimeError(
                "FEATURE_SELECTION_MODE=include selected zero features. "
                "Check INCLUDE_FEATURE_NAMES and INCLUDE_FEATURE_PREFIXES."
            )

    elif FEATURE_SELECTION_MODE == "exclude":
        feature_cols = [
            col
            for col in feature_cols
            if not is_custom_excluded_feature(col)
        ]
        selection_removed_count = before_selection_count - len(feature_cols)

        if not feature_cols:
            raise RuntimeError(
                "FEATURE_SELECTION_MODE=exclude removed all features. "
                "Check EXCLUDE_FEATURE_NAMES and EXCLUDE_FEATURE_PREFIXES."
            )

    else:
        selection_removed_count = 0

    print(
        f"Using {len(feature_cols):,} numeric feature columns. "
        f"raw_price_excluded_count={raw_price_excluded_count} | "
        f"FEATURE_SELECTION_MODE={FEATURE_SELECTION_MODE} | "
        f"selection_removed_count={selection_removed_count} | "
        f"feature_set_suffix={get_feature_set_suffix()}",
        flush=True,
    )

    print(
        f"Feature selection config | "
        f"include_names={get_feature_config_string(INCLUDE_FEATURE_NAMES)} | "
        f"include_prefixes={get_feature_config_string(INCLUDE_FEATURE_PREFIXES)} | "
        f"exclude_names={get_feature_config_string(EXCLUDE_FEATURE_NAMES)} | "
        f"exclude_prefixes={get_feature_config_string(EXCLUDE_FEATURE_PREFIXES)} | "
        f"feature_test_label={FEATURE_TEST_LABEL}",
        flush=True,
    )

    return feature_cols


# ============================================================
# MODEL TRAINING + PREDICTION
# ============================================================

def train_models(train_df, feature_cols, horizon, model_params):
    """
    Trains two Extra Trees models for one horizon:

    1. ExtraTreesRegressor:
       Predicts future return percentage as decimal.
       Example:
           0.05 = +5%
           -0.03 = -3%

    2. ExtraTreesClassifier:
       Predicts probability of loss.
    """

    target_return_col = f"target_return_{horizon}d"
    target_loss_col = f"target_loss_{horizon}d"

    train_df = train_df.dropna(subset=feature_cols + [target_return_col, target_loss_col])

    if len(train_df) < 100:
        return None, None

    X_train = train_df[feature_cols]
    y_return = train_df[target_return_col]
    y_loss = train_df[target_loss_col].astype(int)

    return_model = ExtraTreesRegressor(
        n_estimators=model_params["n_estimators"],
        max_depth=model_params["max_depth"],
        min_samples_leaf=model_params["min_samples_leaf"],
        max_features=model_params.get("max_features", 1.0),
        random_state=model_params["random_state"],
        n_jobs=-1,
        bootstrap=False,
    )

    return_model.fit(X_train, y_return)

    if y_loss.nunique() >= 2:
        loss_model = ExtraTreesClassifier(
            n_estimators=model_params["n_estimators"],
            max_depth=model_params["max_depth"],
            min_samples_leaf=model_params["min_samples_leaf"],
            max_features=model_params.get("max_features", 1.0),
            random_state=model_params["random_state"],
            n_jobs=-1,
            class_weight="balanced",
            bootstrap=False,
        )

        loss_model.fit(X_train, y_loss)
    else:
        loss_model = None

    return return_model, loss_model


def predict_one_row(return_model, loss_model, row, feature_cols):
    X = row[feature_cols]

    return_prediction = float(return_model.predict(X)[0])

    if loss_model is not None:
        proba = loss_model.predict_proba(X)[0]
        class_labels = list(loss_model.classes_)

        if 1 in class_labels:
            loss_index = class_labels.index(1)
            loss_probability = float(proba[loss_index])
        else:
            loss_probability = 0.5
    else:
        loss_probability = 0.5

    confidence_no_loss = 1 - loss_probability

    return return_prediction, confidence_no_loss, loss_probability


def get_leak_safe_training_df(symbol_df, training_start_date, prediction_feature_date, horizon):
    """
    Prevents target leakage.

    At prediction_feature_date, we only know historical rows whose future target date
    is <= prediction_feature_date.
    """

    actual_date_col = f"actual_{horizon}d_date"

    train_df = symbol_df[
        (symbol_df["date"] >= training_start_date)
        & (symbol_df[actual_date_col] <= prediction_feature_date)
    ].copy()

    return train_df


# ============================================================
# BACKTESTING
# ============================================================

def build_ordered_output_row(output_row):
    ordered_cols = [
        "run_timestamp",
        "backtest_name",
        "model_name",
        "base_backtest_name",
        "feature_set_suffix",
        "exclude_raw_price_level_features",
        "feature_selection_mode",
        "include_feature_names",
        "include_feature_prefixes",
        "exclude_feature_names",
        "exclude_feature_prefixes",
        "feature_test_label",
        "additional_backtest_suffix",
        "backtest_duration_months",
        "backtest_start_date_config",
        "backtest_end_date_config",
        "feature_1",
        "feature_2",
        "feature_3",
        "feature_4",
        "feature_5",
        "n_estimators",
        "max_depth",
        "min_samples_leaf",
        "random_state",
        "symbol",
        "training_start_date",
        "training_end_date",
        "test_start_date",
        "test_end_date",
        "previous_trading_date",
        "previous_close_before_test_start",
        "regime_filter_enabled",
        "regime_ok",
        "regime_trend_ok",
        "regime_momentum_ok",
        "regime_volatility_ok",
        "regime_ma_ratio_28",
        "regime_return_20d_past",
        "regime_high_low_range",
        "regime_min_ma_ratio_28_threshold",
        "regime_min_return_20d_threshold",
        "regime_max_high_low_range_threshold",
    ]

    for horizon in HORIZONS:
        ordered_cols += [
            f"{horizon}d_return_pct_pred",
            f"{horizon}d_return_pct_actual",
            f"{horizon}d_close_actual",
            f"{horizon}d_confidence_no_loss",
            f"{horizon}d_loss_probability",
            f"{horizon}d_raw_pred_positive",
            f"{horizon}d_regime_filtered_buy",
            f"{horizon}d_count_pred_positive",
            f"{horizon}d_count_pred_positive_w_actual_positive",
            f"{horizon}d_buy_profit_pct",
        ]
    
    ordered_cols += get_success_metric_columns(HORIZONS)

    ordered_cols += [
        "average_return_pct_pred",
        "average_return_pct_actual",
        "average_close_actual",
        "average_confidence_no_loss",
        "average_loss_probability",
        "average_return_pct_model_on",
        "average_return_pct_model_off",
        "average_profitable_model_on",
        "average_profitable_model_off",
        "sum_count_pred_positive",
        "sum_count_pred_positive_w_actual_positive",
        "overall_buy_profit_pct",
    ]

    ordered_row = {}

    for col in ordered_cols:
        ordered_row[col] = output_row.get(col, np.nan)

    return ordered_row


def run_backtest(features, model_params, output_path):
    effective_backtest_name = get_effective_backtest_name(model_params["backtest_name"])

    print(f"\nRunning backtest: {effective_backtest_name}", flush=True)

    results = []
    feature_importance_rows = []

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])

    for horizon in HORIZONS:
        features[f"actual_{horizon}d_date"] = pd.to_datetime(
            features[f"actual_{horizon}d_date"]
        )

    backtest_start = pd.to_datetime(BACKTEST_START_DATE)
    backtest_end = pd.to_datetime(BACKTEST_END_DATE)

    feature_cols = get_feature_columns(features)

    for symbol in SYMBOLS:
        print(f"Backtesting symbol: {symbol}", flush=True)

        symbol_df = features[features["symbol"] == symbol].copy()
        symbol_df = symbol_df.sort_values("date").reset_index(drop=True)

        test_dates = symbol_df[
            (symbol_df["date"] >= backtest_start)
            & (symbol_df["date"] <= backtest_end)
        ]["date"].unique()

        if SMOKE_TEST:
            print(
                f"SMOKE_TEST enabled: only testing first "
                f"{SMOKE_TEST_DAYS_PER_SYMBOL} dates per symbol.",
                flush=True,
            )
            test_dates = test_dates[:SMOKE_TEST_DAYS_PER_SYMBOL]

        for test_date in test_dates:
            test_date = pd.to_datetime(test_date)

            test_rows = symbol_df[symbol_df["date"] == test_date]

            if test_rows.empty:
                print("    Skipped: empty test row.", flush=True)
                continue

            test_row_index = test_rows.index[0]

            if test_row_index == 0:
                print("    Skipped: no previous trading day available.", flush=True)
                continue

            # ------------------------------------------------------------
            # NO-LEAK SETUP
            # ------------------------------------------------------------
            # Prediction input row is the PREVIOUS trading day.
            # We do not use the current/test-day close as a feature.
            # ------------------------------------------------------------
            previous_row = symbol_df.iloc[[test_row_index - 1]].copy()
            previous_trading_date = pd.to_datetime(previous_row.iloc[0]["date"])
            previous_close_before_test_start = float(previous_row.iloc[0]["close"])
            regime_flags = get_market_regime_flags(previous_row)

            if previous_row[feature_cols].isna().any(axis=None):
                print("    Skipped: previous row has missing feature values.", flush=True)
                continue

            training_end_date = previous_trading_date
            training_start_date = previous_trading_date - timedelta(days=365)

            print(
                f"  Testing date: {test_date.date()} | "
                f"prediction input date={previous_trading_date.date()} | "
                f"backtest={effective_backtest_name} | "
                f"symbol={symbol}",
                flush=True,
            )

            output_row = {
                "run_timestamp": RUN_TIMESTAMP,
                "backtest_name": effective_backtest_name,
                "base_backtest_name": model_params["backtest_name"],
                "model_name": MODEL_NAME,
                "feature_set_suffix": get_feature_set_suffix(),
                "exclude_raw_price_level_features": bool(EXCLUDE_RAW_PRICE_LEVEL_FEATURES),
                "feature_selection_mode": FEATURE_SELECTION_MODE,
                "include_feature_names": get_feature_config_string(INCLUDE_FEATURE_NAMES),
                "include_feature_prefixes": get_feature_config_string(INCLUDE_FEATURE_PREFIXES),
                "exclude_feature_names": get_feature_config_string(EXCLUDE_FEATURE_NAMES),
                "exclude_feature_prefixes": get_feature_config_string(EXCLUDE_FEATURE_PREFIXES),
                "feature_test_label": FEATURE_TEST_LABEL,
                "additional_backtest_suffix": get_additional_backtest_suffix(),
                "backtest_duration_months": BACKTEST_DURATION_MONTHS,
                "backtest_start_date_config": BACKTEST_START_DATE,
                "backtest_end_date_config": BACKTEST_END_DATE,
                "feature_1": None,
                "feature_2": None,
                "feature_3": None,
                "feature_4": None,
                "feature_5": None,
                "n_estimators": model_params["n_estimators"],
                "max_depth": model_params["max_depth"],
                "min_samples_leaf": model_params["min_samples_leaf"],
                "random_state": model_params["random_state"],
                "symbol": symbol,
                "training_start_date": training_start_date.date(),
                "training_end_date": training_end_date.date(),
                "test_start_date": test_date.date(),
                "test_end_date": None,
                "previous_trading_date": previous_trading_date.date(),
                "previous_close_before_test_start": previous_close_before_test_start,
                "regime_filter_enabled": regime_flags["regime_filter_enabled"],
                "regime_ok": regime_flags["regime_ok"],
                "regime_trend_ok": regime_flags["regime_trend_ok"],
                "regime_momentum_ok": regime_flags["regime_momentum_ok"],
                "regime_volatility_ok": regime_flags["regime_volatility_ok"],
                "regime_ma_ratio_28": regime_flags["regime_ma_ratio_28"],
                "regime_return_20d_past": regime_flags["regime_return_20d_past"],
                "regime_high_low_range": regime_flags["regime_high_low_range"],
                "regime_min_ma_ratio_28_threshold": regime_flags["regime_min_ma_ratio_28_threshold"],
                "regime_min_return_20d_threshold": regime_flags["regime_min_return_20d_threshold"],
                "regime_max_high_low_range_threshold": regime_flags["regime_max_high_low_range_threshold"],
            }

            return_predictions = []
            actual_returns = []
            actual_closes = []
            confidence_no_loss_values = []
            loss_probability_values = []
            model_on_returns = []
            model_off_returns = []
            model_on_profitable_values = []
            model_off_profitable_values = []
            pred_positive_counts = []
            pred_positive_actual_positive_counts = []
            feature_importance_arrays = []
            max_test_end_date = None

            row_is_complete = True

            for horizon in HORIZONS:
                actual_close_col = f"actual_{horizon}d_close"
                actual_date_col = f"actual_{horizon}d_date"

                actual_close = previous_row.iloc[0][actual_close_col]
                actual_end_date = previous_row.iloc[0][actual_date_col]

                if pd.isna(actual_close) or pd.isna(actual_end_date):
                    print(
                        f"    Skipped row: no actual available for {horizon}d.",
                        flush=True,
                    )
                    row_is_complete = False
                    break

                train_df = get_leak_safe_training_df(
                    symbol_df=symbol_df,
                    training_start_date=training_start_date,
                    prediction_feature_date=previous_trading_date,
                    horizon=horizon,
                )

                return_model, loss_model = train_models(
                    train_df=train_df,
                    feature_cols=feature_cols,
                    horizon=horizon,
                    model_params=model_params,
                )

                if return_model is None:
                    print(
                        f"    Skipped row: not enough training rows for {horizon}d.",
                        flush=True,
                    )
                    row_is_complete = False
                    break

                return_pct_pred, confidence_no_loss, loss_probability = predict_one_row(
                    return_model=return_model,
                    loss_model=loss_model,
                    row=previous_row,
                    feature_cols=feature_cols,
                )

                actual_close = float(actual_close)

                return_pct_actual = (
                    actual_close / previous_close_before_test_start
                ) - 1

                raw_pred_positive = return_pct_pred > 0
                model_buy_signal = apply_market_regime_filter(
                    raw_pred_positive=raw_pred_positive,
                    regime_flags=regime_flags,
                )

                count_pred_positive = int(model_buy_signal)
                count_pred_positive_w_actual_positive = int(
                    model_buy_signal and return_pct_actual > 0
                )

                output_row = add_horizon_success_metrics(
                    output_row=output_row,
                    horizon=horizon,
                    return_pct_pred=return_pct_pred,
                    return_pct_actual=return_pct_actual,
                    loss_probability=loss_probability,
                    model_buy_signal=model_buy_signal,
                )

                buy_profit_pct = safe_divide(
                    count_pred_positive_w_actual_positive,
                    count_pred_positive,
                )

                output_row[f"{horizon}d_return_pct_pred"] = return_pct_pred
                output_row[f"{horizon}d_return_pct_actual"] = return_pct_actual
                output_row[f"{horizon}d_close_actual"] = actual_close
                output_row[f"{horizon}d_confidence_no_loss"] = confidence_no_loss
                output_row[f"{horizon}d_loss_probability"] = loss_probability
                output_row[f"{horizon}d_raw_pred_positive"] = int(raw_pred_positive)
                output_row[f"{horizon}d_regime_filtered_buy"] = int(model_buy_signal)
                output_row[f"{horizon}d_count_pred_positive"] = count_pred_positive
                output_row[
                    f"{horizon}d_count_pred_positive_w_actual_positive"
                ] = count_pred_positive_w_actual_positive
                output_row[f"{horizon}d_buy_profit_pct"] = buy_profit_pct

                # ------------------------------------------------------------
                # FEATURE IMPORTANCE AUDIT
                # ------------------------------------------------------------
                # Log native importances for the fitted return regressor and,
                # optionally, the fitted loss classifier. These rows are later
                # written once per parameter combination to avoid excessive I/O.
                feature_importance_rows.extend(
                    build_feature_importance_rows(
                        model=return_model,
                        feature_cols=feature_cols,
                        run_timestamp=RUN_TIMESTAMP,
                        model_name=MODEL_NAME,
                        backtest_name=effective_backtest_name,
                        symbol=symbol,
                        test_start_date=test_date.date(),
                        prediction_input_date=previous_trading_date.date(),
                        horizon=horizon,
                        model_component="return_regressor",
                        return_pct_pred=return_pct_pred,
                        return_pct_actual=return_pct_actual,
                        confidence_no_loss=confidence_no_loss,
                        loss_probability=loss_probability,
                        raw_pred_positive=raw_pred_positive,
                        regime_filtered_buy=model_buy_signal,
                    )
                )

                if LOG_LOSS_MODEL_IMPORTANCE and loss_model is not None:
                    feature_importance_rows.extend(
                        build_feature_importance_rows(
                            model=loss_model,
                            feature_cols=feature_cols,
                            run_timestamp=RUN_TIMESTAMP,
                            model_name=MODEL_NAME,
                            backtest_name=effective_backtest_name,
                            symbol=symbol,
                            test_start_date=test_date.date(),
                            prediction_input_date=previous_trading_date.date(),
                            horizon=horizon,
                            model_component="loss_classifier",
                            return_pct_pred=return_pct_pred,
                            return_pct_actual=return_pct_actual,
                            confidence_no_loss=confidence_no_loss,
                            loss_probability=loss_probability,
                            raw_pred_positive=raw_pred_positive,
                            regime_filtered_buy=model_buy_signal,
                        )
                    )

                return_predictions.append(return_pct_pred)
                actual_returns.append(return_pct_actual)
                actual_closes.append(actual_close)
                confidence_no_loss_values.append(confidence_no_loss)
                loss_probability_values.append(loss_probability)
                pred_positive_counts.append(count_pred_positive)
                pred_positive_actual_positive_counts.append(
                    count_pred_positive_w_actual_positive
                )

                feature_importance_arrays.append(return_model.feature_importances_)

                actual_end_date = pd.to_datetime(actual_end_date)

                if max_test_end_date is None:
                    max_test_end_date = actual_end_date
                else:
                    max_test_end_date = max(max_test_end_date, actual_end_date)

            if not row_is_complete:
                continue

            top_features = get_top_features_from_importances(
                feature_cols=feature_cols,
                importance_arrays=feature_importance_arrays,
                top_n=5,
            )

            output_row["feature_1"] = top_features[0]
            output_row["feature_2"] = top_features[1]
            output_row["feature_3"] = top_features[2]
            output_row["feature_4"] = top_features[3]
            output_row["feature_5"] = top_features[4]

            output_row["test_end_date"] = max_test_end_date.date()

            output_row["average_return_pct_pred"] = float(np.mean(return_predictions))
            output_row["average_return_pct_actual"] = float(np.mean(actual_returns))
            output_row["average_close_actual"] = float(np.mean(actual_closes))
            output_row["average_confidence_no_loss"] = float(
                np.mean(confidence_no_loss_values)
            )
            output_row["average_loss_probability"] = float(
                np.mean(loss_probability_values)
            )

            output_row = add_average_success_metrics(output_row, HORIZONS)

            output_row["sum_count_pred_positive"] = int(np.sum(pred_positive_counts))
            output_row["sum_count_pred_positive_w_actual_positive"] = int(
                np.sum(pred_positive_actual_positive_counts)
            )

            output_row["overall_buy_profit_pct"] = safe_divide(
                output_row["sum_count_pred_positive_w_actual_positive"],
                output_row["sum_count_pred_positive"],
            )

            ordered_row = build_ordered_output_row(output_row)

            results.append(ordered_row)
            append_row_to_csv(ordered_row, output_path)

            print(
                f"    Appended result | "
                f"{effective_backtest_name} | "
                f"{symbol} | "
                f"test_start={test_date.date()} | "
                f"prev_close={previous_close_before_test_start:.4f} | "
                f"avg_pred_return={output_row['average_return_pct_pred']:.2%} | "
                f"avg_actual_return={output_row['average_return_pct_actual']:.2%} | "
                f"overall_buy_profit_pct={output_row['overall_buy_profit_pct']}",
                flush=True,
            )

    write_feature_importance_outputs(feature_importance_rows)

    backtest_results = pd.DataFrame(results)

    if backtest_results.empty:
        print(f"No backtest results created for {effective_backtest_name}.", flush=True)
        return backtest_results

    backtest_results = backtest_results.sort_values(
        ["backtest_name", "symbol", "test_start_date"]
    ).reset_index(drop=True)

    print(
        f"Backtest {effective_backtest_name} created "
        f"{len(backtest_results):,} rows.",
        flush=True,
    )

    return backtest_results


def run_backtest_grid(features):
    parameter_grid = PARAMETER_GRID

    if SMOKE_TEST:
        print(
            f"SMOKE_TEST enabled: using first "
            f"{SMOKE_TEST_PARAMETER_COUNT} parameter combinations.",
            flush=True,
        )
        parameter_grid = PARAMETER_GRID[:SMOKE_TEST_PARAMETER_COUNT]

    all_results = []

    for i, model_params in enumerate(parameter_grid, start=1):
        print(
            f"\nStarting parameter combination {i}/{len(parameter_grid)}: "
            f"{model_params['backtest_name']}",
            flush=True,
        )

        combo_results = run_backtest(
            features=features,
            model_params=model_params,
            output_path=BACKTEST_OUTPUT_PATH,
        )

        if not combo_results.empty:
            all_results.append(combo_results)

    if all_results:
        all_backtest_results = pd.concat(all_results, ignore_index=True)
        print(
            f"\nAll backtests complete. Total rows: {len(all_backtest_results):,}",
            flush=True,
        )
        return all_backtest_results

    print("\nAll backtests complete, but no rows were created.", flush=True)
    return pd.DataFrame()


def summarise_backtest(backtest_results):
    if backtest_results.empty:
        return

    print("\nBacktest summary:", flush=True)

    for backtest_name in sorted(backtest_results["backtest_name"].unique()):
        bt_df = backtest_results[backtest_results["backtest_name"] == backtest_name]

        print(f"\nBacktest: {backtest_name}", flush=True)

        for symbol in SYMBOLS:
            symbol_df = bt_df[bt_df["symbol"] == symbol]

            if symbol_df.empty:
                continue

            print(f"  Symbol: {symbol}", flush=True)

            for horizon in HORIZONS:
                pred_col = f"{horizon}d_return_pct_pred"
                actual_col = f"{horizon}d_return_pct_actual"

                valid = symbol_df.dropna(subset=[pred_col, actual_col])

                if valid.empty:
                    continue

                mae = mean_absolute_error(valid[actual_col], valid[pred_col])
                rmse = np.sqrt(mean_squared_error(valid[actual_col], valid[pred_col]))

                pred_positive_count = valid[f"{horizon}d_count_pred_positive"].sum()
                pred_positive_actual_positive_count = valid[
                    f"{horizon}d_count_pred_positive_w_actual_positive"
                ].sum()

                buy_profit_pct = safe_divide(
                    pred_positive_actual_positive_count,
                    pred_positive_count,
                )

                avg_pred = valid[pred_col].mean()
                avg_actual = valid[actual_col].mean()

                print(
                    f"    {horizon}d | "
                    f"MAE={mae:.4%} | "
                    f"RMSE={rmse:.4%} | "
                    f"avg_pred={avg_pred:.2%} | "
                    f"avg_actual={avg_actual:.2%} | "
                    f"buy_profit_pct={buy_profit_pct}",
                    flush=True,
                )


# ============================================================
# PRODUCTION FORECAST
# ============================================================

def run_production_forecast(features):
    print("\nRunning production forecast...", flush=True)

    results = []

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])

    for horizon in HORIZONS:
        features[f"actual_{horizon}d_date"] = pd.to_datetime(
            features[f"actual_{horizon}d_date"]
        )

    feature_cols = get_feature_columns(features)

    forecast_date = datetime.utcnow().date()
    model_params = PRODUCTION_MODEL_PARAMS

    effective_production_model_name = get_effective_backtest_name(model_params["backtest_name"])

    print(
        f"Production model params: {effective_production_model_name}",
        flush=True,
    )

    for symbol in SYMBOLS:
        print(f"Production forecast for {symbol}...", flush=True)

        symbol_df = features[features["symbol"] == symbol].copy()
        symbol_df = symbol_df.sort_values("date").reset_index(drop=True)

        latest_row = symbol_df.dropna(subset=feature_cols).tail(1).copy()

        if latest_row.empty:
            print(f"  Skipped {symbol}: no valid latest row.", flush=True)
            continue

        latest_date = pd.to_datetime(latest_row.iloc[0]["date"])
        latest_close = float(latest_row.iloc[0]["close"])
        regime_flags = get_market_regime_flags(latest_row)

        training_start_date = latest_date - timedelta(days=365)

        output_row = {
            "forecast_date": forecast_date,
            "model_name": MODEL_NAME,
            "data_as_of_date": latest_date.date(),
            "stock_symbol": symbol,
            "stock_start_value": float(latest_row.iloc[0]["open"]),
            "stock_end_value": latest_close,
            "production_model_name": effective_production_model_name,
            "production_model_base_name": model_params["backtest_name"],
            "feature_set_suffix": get_feature_set_suffix(),
            "exclude_raw_price_level_features": bool(EXCLUDE_RAW_PRICE_LEVEL_FEATURES),
            "feature_selection_mode": FEATURE_SELECTION_MODE,
            "include_feature_names": get_feature_config_string(INCLUDE_FEATURE_NAMES),
            "include_feature_prefixes": get_feature_config_string(INCLUDE_FEATURE_PREFIXES),
            "exclude_feature_names": get_feature_config_string(EXCLUDE_FEATURE_NAMES),
            "exclude_feature_prefixes": get_feature_config_string(EXCLUDE_FEATURE_PREFIXES),
            "feature_test_label": FEATURE_TEST_LABEL,
            "n_estimators": model_params["n_estimators"],
            "max_depth": model_params["max_depth"],
            "min_samples_leaf": model_params["min_samples_leaf"],
            "random_state": model_params["random_state"],
            "regime_filter_enabled": regime_flags["regime_filter_enabled"],
            "regime_ok": regime_flags["regime_ok"],
            "regime_trend_ok": regime_flags["regime_trend_ok"],
            "regime_momentum_ok": regime_flags["regime_momentum_ok"],
            "regime_volatility_ok": regime_flags["regime_volatility_ok"],
            "regime_ma_ratio_28": regime_flags["regime_ma_ratio_28"],
            "regime_return_20d_past": regime_flags["regime_return_20d_past"],
            "regime_high_low_range": regime_flags["regime_high_low_range"],
            "regime_min_ma_ratio_28_threshold": regime_flags["regime_min_ma_ratio_28_threshold"],
            "regime_min_return_20d_threshold": regime_flags["regime_min_return_20d_threshold"],
            "regime_max_high_low_range_threshold": regime_flags["regime_max_high_low_range_threshold"],
        }

        for horizon in HORIZONS:
            train_df = get_leak_safe_training_df(
                symbol_df=symbol_df,
                training_start_date=training_start_date,
                prediction_feature_date=latest_date,
                horizon=horizon,
            )

            return_model, loss_model = train_models(
                train_df=train_df,
                feature_cols=feature_cols,
                horizon=horizon,
                model_params=model_params,
            )

            if return_model is None:
                output_row[f"{horizon}d_return_pct_pred"] = np.nan
                output_row[f"{horizon}d_close_pred"] = np.nan
                output_row[f"{horizon}d_confidence_no_loss"] = np.nan
                output_row[f"{horizon}d_loss_probability"] = np.nan
                continue

            return_pct_pred, confidence_no_loss, loss_probability = predict_one_row(
                return_model=return_model,
                loss_model=loss_model,
                row=latest_row,
                feature_cols=feature_cols,
            )

            close_pred = latest_close * (1 + return_pct_pred)

            output_row[f"{horizon}d_return_pct_pred"] = return_pct_pred
            output_row[f"{horizon}d_close_pred"] = close_pred
            output_row[f"{horizon}d_confidence_no_loss"] = confidence_no_loss
            output_row[f"{horizon}d_loss_probability"] = loss_probability

            raw_pred_positive = return_pct_pred > 0
            model_buy_signal = apply_market_regime_filter(
                raw_pred_positive=raw_pred_positive,
                regime_flags=regime_flags,
            )

            output_row[f"{horizon}d_raw_pred_positive"] = int(raw_pred_positive)
            output_row[f"{horizon}d_regime_filtered_buy"] = int(model_buy_signal)

        results.append(output_row)

    production_forecast = pd.DataFrame(results)

    for _, row in production_forecast.iterrows():
        append_row_to_csv(row.to_dict(), PRODUCTION_OUTPUT_PATH)

    print(f"Production forecast created {len(production_forecast):,} rows.", flush=True)
    print(f"Appended production forecast to: {PRODUCTION_OUTPUT_PATH}", flush=True)

    return production_forecast


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_output_dir()

    print("Market regime filter config:", flush=True)
    print(f"  USE_MARKET_REGIME_FILTER={USE_MARKET_REGIME_FILTER}", flush=True)
    print(f"  REGIME_MIN_MA_RATIO_28={REGIME_MIN_MA_RATIO_28}", flush=True)
    print(f"  REGIME_MIN_RETURN_20D={REGIME_MIN_RETURN_20D}", flush=True)
    print(f"  REGIME_MAX_HIGH_LOW_RANGE={REGIME_MAX_HIGH_LOW_RANGE}", flush=True)
    print(f"  EXCLUDE_RAW_PRICE_LEVEL_FEATURES={EXCLUDE_RAW_PRICE_LEVEL_FEATURES}", flush=True)
    print(f"  FEATURE_SELECTION_MODE={FEATURE_SELECTION_MODE}", flush=True)
    print(f"  INCLUDE_FEATURE_NAMES={get_feature_config_string(INCLUDE_FEATURE_NAMES)}", flush=True)
    print(f"  INCLUDE_FEATURE_PREFIXES={get_feature_config_string(INCLUDE_FEATURE_PREFIXES)}", flush=True)
    print(f"  EXCLUDE_FEATURE_NAMES={get_feature_config_string(EXCLUDE_FEATURE_NAMES)}", flush=True)
    print(f"  EXCLUDE_FEATURE_PREFIXES={get_feature_config_string(EXCLUDE_FEATURE_PREFIXES)}", flush=True)
    print(f"  FEATURE_TEST_LABEL={FEATURE_TEST_LABEL}", flush=True)
    print(f"  ADDITIONAL_BACKTEST_SUFFIX={get_additional_backtest_suffix()}", flush=True)
    print(f"  BACKTEST_DURATION_MONTHS={BACKTEST_DURATION_MONTHS}", flush=True)
    print(f"  BACKTEST_START_DATE={BACKTEST_START_DATE}", flush=True)
    print(f"  BACKTEST_END_DATE={BACKTEST_END_DATE}", flush=True)
    print(f"  FEATURE_SET_SUFFIX={get_feature_set_suffix()}", flush=True)

    raw_data = download_data(SYMBOLS)
    clean = clean_data(raw_data)
    clean = add_cross_symbol_features(clean)
    features = create_features(clean)

    backtest_results = run_backtest_grid(features)
    summarise_backtest(backtest_results)

    run_production_forecast(features)

    print(f"\nSaved backtest results to: {BACKTEST_OUTPUT_PATH}")
    print(f"Appended production forecast to: {PRODUCTION_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
