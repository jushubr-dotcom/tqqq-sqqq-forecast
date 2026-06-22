import os
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
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

BACKTEST_START_DATE = "2026-01-01"
BACKTEST_END_DATE = "2026-05-31"

OUTPUT_DIR = "outputs"
BACKTEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "backtest_results.csv")
PRODUCTION_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "production_forecast.csv")

SMOKE_TEST = os.getenv("SMOKE_TEST", "false").lower() == "true"
SMOKE_TEST_DAYS_PER_SYMBOL = int(os.getenv("SMOKE_TEST_DAYS_PER_SYMBOL", "10"))
SMOKE_TEST_PARAMETER_COUNT = int(os.getenv("SMOKE_TEST_PARAMETER_COUNT", "2"))

MODEL_NAME = os.getenv("MODEL_NAME", "ElasticNet")


# ============================================================
# ELASTICNET PARAMETER GRID
# ============================================================

PARAMETER_GRID = [
    {"backtest_name": "elasticnet_alpha001_l1_01_logreg_C001_6m", "alpha": 0.01, "l1_ratio": 0.1, "logreg_C": 0.01, "random_state": 42},
    {"backtest_name": "elasticnet_alpha001_l1_05_logreg_C001_6m", "alpha": 0.01, "l1_ratio": 0.5, "logreg_C": 0.01, "random_state": 42},
    {"backtest_name": "elasticnet_alpha001_l1_09_logreg_C001_6m", "alpha": 0.01, "l1_ratio": 0.9, "logreg_C": 0.01, "random_state": 42},

    {"backtest_name": "elasticnet_alpha01_l1_01_logreg_C001_6m", "alpha": 0.1, "l1_ratio": 0.1, "logreg_C": 0.01, "random_state": 42},
    {"backtest_name": "elasticnet_alpha01_l1_05_logreg_C001_6m", "alpha": 0.1, "l1_ratio": 0.5, "logreg_C": 0.01, "random_state": 42},
    {"backtest_name": "elasticnet_alpha01_l1_09_logreg_C001_6m", "alpha": 0.1, "l1_ratio": 0.9, "logreg_C": 0.01, "random_state": 42},

    {"backtest_name": "elasticnet_alpha1_l1_01_logreg_C001_6m", "alpha": 1.0, "l1_ratio": 0.1, "logreg_C": 0.01, "random_state": 42},
    {"backtest_name": "elasticnet_alpha1_l1_05_logreg_C001_6m", "alpha": 1.0, "l1_ratio": 0.5, "logreg_C": 0.01, "random_state": 42},

    {"backtest_name": "elasticnet_alpha01_l1_05_logreg_C005_6m", "alpha": 0.1, "l1_ratio": 0.5, "logreg_C": 0.05, "random_state": 42},
    {"backtest_name": "elasticnet_alpha01_l1_05_logreg_C01_6m", "alpha": 0.1, "l1_ratio": 0.5, "logreg_C": 0.1, "random_state": 42},
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


def get_top_features_from_coefficients(feature_cols, coefficient_arrays, top_n=5):
    """
    For ElasticNet, feature ranking uses absolute coefficient size after scaling.
    Larger absolute coefficient = stronger linear contribution.
    """
    if not coefficient_arrays:
        return [None] * top_n

    coef_matrix = np.vstack(coefficient_arrays)
    avg_abs_coef = np.abs(coef_matrix).mean(axis=0)

    ranked_indices = np.argsort(avg_abs_coef)[::-1]
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

        df["daily_return"] = df["close"].pct_change()
        df["open_to_close_return"] = (df["close"] - df["open"]) / df["open"]
        df["high_low_range"] = (df["high"] - df["low"]) / df["close"]

        for lag in LAG_DAYS:
            df[f"close_lag_{lag}"] = df["close"].shift(lag)
            df[f"return_lag_{lag}"] = df["daily_return"].shift(lag)

        for window in [7, 14, 28]:
            df[f"ma_{window}"] = df["close"].rolling(window=window).mean()
            df[f"ma_ratio_{window}"] = df["close"] / df[f"ma_{window}"]

        for window in RETURN_WINDOWS:
            df[f"return_{window}d_past"] = df["close"].pct_change(window)

        df["other_symbol_return"] = df["other_symbol_close"].pct_change()

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

    feature_cols = [
        col
        for col in df.columns
        if col not in excluded_cols
        and pd.api.types.is_numeric_dtype(df[col])
    ]

    return feature_cols


# ============================================================
# MODEL TRAINING + PREDICTION
# ============================================================

def train_models(train_df, feature_cols, horizon, model_params):
    """
    Trains two linear models for one horizon:

    1. ElasticNet:
       Predicts future return percentage as decimal.
       Example:
           0.05 = +5%
           -0.03 = -3%

    2. LogisticRegression:
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

    return_model = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "elasticnet",
                ElasticNet(
                    alpha=model_params["alpha"],
                    l1_ratio=model_params["l1_ratio"],
                    random_state=model_params["random_state"],
                    max_iter=10000,
                ),
            ),
        ]
    )

    return_model.fit(X_train, y_return)

    if y_loss.nunique() >= 2:
        loss_model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "logreg",
                    LogisticRegression(
                        C=model_params["logreg_C"],
                        class_weight="balanced",
                        random_state=model_params["random_state"],
                        max_iter=5000,
                        solver="lbfgs",
                    ),
                ),
            ]
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


def get_elasticnet_coefficients(return_model):
    """
    Pulls coefficients from the fitted ElasticNet pipeline.
    Because we use StandardScaler, coefficients are comparable across features.
    """
    elasticnet_model = return_model.named_steps["elasticnet"]
    return elasticnet_model.coef_


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
        "feature_1",
        "feature_2",
        "feature_3",
        "feature_4",
        "feature_5",
        "alpha",
        "l1_ratio",
        "logreg_C",
        "random_state",
        "symbol",
        "training_start_date",
        "training_end_date",
        "test_start_date",
        "test_end_date",
        "previous_trading_date",
        "previous_close_before_test_start",
    ]

    for horizon in HORIZONS:
        ordered_cols += [
            f"{horizon}d_return_pct_pred",
            f"{horizon}d_return_pct_actual",
            f"{horizon}d_close_actual",
            f"{horizon}d_confidence_no_loss",
            f"{horizon}d_loss_probability",
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
        "sum_count_pred_positive",
        "sum_count_pred_positive_w_actual_positive",
        "overall_buy_profit_pct",
    ]

    ordered_row = {}

    for col in ordered_cols:
        ordered_row[col] = output_row.get(col, np.nan)

    return ordered_row


def run_backtest(features, model_params, output_path):
    print(f"\nRunning backtest: {model_params['backtest_name']}", flush=True)

    results = []

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

            previous_row = symbol_df.iloc[[test_row_index - 1]].copy()
            previous_trading_date = pd.to_datetime(previous_row.iloc[0]["date"])
            previous_close_before_test_start = float(previous_row.iloc[0]["close"])

            if previous_row[feature_cols].isna().any(axis=None):
                print("    Skipped: previous row has missing feature values.", flush=True)
                continue

            training_end_date = previous_trading_date
            training_start_date = previous_trading_date - timedelta(days=365)

            print(
                f"  Testing date: {test_date.date()} | "
                f"prediction input date={previous_trading_date.date()} | "
                f"backtest={model_params['backtest_name']} | "
                f"symbol={symbol}",
                flush=True,
            )

            output_row = {
                "run_timestamp": RUN_TIMESTAMP,
                "backtest_name": model_params["backtest_name"],
                "model_name": MODEL_NAME,
                "feature_1": None,
                "feature_2": None,
                "feature_3": None,
                "feature_4": None,
                "feature_5": None,
                "alpha": model_params["alpha"],
                "l1_ratio": model_params["l1_ratio"],
                "logreg_C": model_params["logreg_C"],
                "random_state": model_params["random_state"],
                "symbol": symbol,
                "training_start_date": training_start_date.date(),
                "training_end_date": training_end_date.date(),
                "test_start_date": test_date.date(),
                "test_end_date": None,
                "previous_trading_date": previous_trading_date.date(),
                "previous_close_before_test_start": previous_close_before_test_start,
            }

            return_predictions = []
            actual_returns = []
            actual_closes = []
            confidence_no_loss_values = []
            loss_probability_values = []
            pred_positive_counts = []
            pred_positive_actual_positive_counts = []
            coefficient_arrays = []
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

                count_pred_positive = int(return_pct_pred > 0)
                count_pred_positive_w_actual_positive = int(
                    return_pct_pred > 0 and return_pct_actual > 0
                )

                buy_profit_pct = safe_divide(
                    count_pred_positive_w_actual_positive,
                    count_pred_positive,
                )

                output_row = add_horizon_success_metrics(
                    output_row=output_row,
                    horizon=horizon,
                    return_pct_pred=return_pct_pred,
                    return_pct_actual=return_pct_actual,
                    loss_probability=loss_probability,
                )

                output_row[f"{horizon}d_return_pct_pred"] = return_pct_pred
                output_row[f"{horizon}d_return_pct_actual"] = return_pct_actual
                output_row[f"{horizon}d_close_actual"] = actual_close
                output_row[f"{horizon}d_confidence_no_loss"] = confidence_no_loss
                output_row[f"{horizon}d_loss_probability"] = loss_probability
                output_row[f"{horizon}d_count_pred_positive"] = count_pred_positive
                output_row[
                    f"{horizon}d_count_pred_positive_w_actual_positive"
                ] = count_pred_positive_w_actual_positive
                output_row[f"{horizon}d_buy_profit_pct"] = buy_profit_pct

                return_predictions.append(return_pct_pred)
                actual_returns.append(return_pct_actual)
                actual_closes.append(actual_close)
                confidence_no_loss_values.append(confidence_no_loss)
                loss_probability_values.append(loss_probability)
                pred_positive_counts.append(count_pred_positive)
                pred_positive_actual_positive_counts.append(
                    count_pred_positive_w_actual_positive
                )

                coefficient_arrays.append(get_elasticnet_coefficients(return_model))

                actual_end_date = pd.to_datetime(actual_end_date)

                if max_test_end_date is None:
                    max_test_end_date = actual_end_date
                else:
                    max_test_end_date = max(max_test_end_date, actual_end_date)

            if not row_is_complete:
                continue

            top_features = get_top_features_from_coefficients(
                feature_cols=feature_cols,
                coefficient_arrays=coefficient_arrays,
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
                f"{model_params['backtest_name']} | "
                f"{symbol} | "
                f"test_start={test_date.date()} | "
                f"prev_close={previous_close_before_test_start:.4f} | "
                f"avg_pred_return={output_row['average_return_pct_pred']:.2%} | "
                f"avg_actual_return={output_row['average_return_pct_actual']:.2%} | "
                f"overall_buy_profit_pct={output_row['overall_buy_profit_pct']}",
                flush=True,
            )

    backtest_results = pd.DataFrame(results)

    if backtest_results.empty:
        print(f"No backtest results created for {model_params['backtest_name']}.", flush=True)
        return backtest_results

    backtest_results = backtest_results.sort_values(
        ["backtest_name", "symbol", "test_start_date"]
    ).reset_index(drop=True)

    print(
        f"Backtest {model_params['backtest_name']} created "
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

    print(
        f"Production model params: {model_params['backtest_name']}",
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

        training_end_date = latest_date
        training_start_date = latest_date - timedelta(days=365)

        output_row = {
            "forecast_date": forecast_date,
            "model_name": MODEL_NAME,
            "data_as_of_date": latest_date.date(),
            "stock_symbol": symbol,
            "stock_start_value": float(latest_row.iloc[0]["open"]),
            "stock_end_value": latest_close,
            "production_model_name": model_params["backtest_name"],
            "alpha": model_params["alpha"],
            "l1_ratio": model_params["l1_ratio"],
            "logreg_C": model_params["logreg_C"],
            "random_state": model_params["random_state"],
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
