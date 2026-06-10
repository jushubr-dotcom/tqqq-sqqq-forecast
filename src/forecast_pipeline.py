import os
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, mean_squared_error


warnings.filterwarnings("ignore")


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = ["TQQQ", "SQQQ"]
HORIZONS = [5, 7, 14, 28]
LAG_DAYS = list(range(1, 53))

BACKTEST_START_DATE = "2026-01-01"
BACKTEST_END_DATE = "2026-05-31"

OUTPUT_DIR = "outputs"
BACKTEST_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "backtest_results.csv")
PRODUCTION_OUTPUT_PATH = os.path.join(OUTPUT_DIR, "production_forecast.csv")

SMOKE_TEST = os.getenv("SMOKE_TEST", "false").lower() == "true"


# Hyperparameter combinations to test.
# Add/remove combinations here.
PARAMETER_GRID = [
    {
        "backtest_name": "rf_10trees_depth4_leaf20",
        "n_estimators": 10,
        "max_depth": 4,
        "min_samples_leaf": 20,
        "random_state": 42,
    },
    {
        "backtest_name": "rf_25trees_depth4_leaf20",
        "n_estimators": 25,
        "max_depth": 4,
        "min_samples_leaf": 20,
        "random_state": 42,
    },
    {
        "backtest_name": "rf_50trees_depth6_leaf20",
        "n_estimators": 50,
        "max_depth": 6,
        "min_samples_leaf": 20,
        "random_state": 42,
    },
]


# Production model parameters.
# For now, use the strongest/last combination.
# Later, you can select this automatically based on best backtest results.
PRODUCTION_MODEL_PARAMS = PARAMETER_GRID[-1]


# ============================================================
# HELPERS
# ============================================================

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def append_row_to_csv(row, output_path):
    """
    Appends one backtest result row to CSV immediately.

    In GitHub Actions, the file will only be pushed to the repo
    at the end of the workflow, but this still writes incrementally
    inside the runner and gives us log visibility as the backtest runs.
    """

    row_df = pd.DataFrame([row])
    file_exists = os.path.exists(output_path)

    row_df.to_csv(
        output_path,
        mode="a",
        header=not file_exists,
        index=False,
    )


# ============================================================
# DATA DOWNLOAD + CLEANING
# ============================================================

def download_data(symbols):
    """
    Downloads 5 years of daily OHLCV data from Yahoo Finance.
    """

    print("Downloading data from Yahoo Finance...", flush=True)

    raw = yf.download(
        tickers=symbols,
        period="5y",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    frames = []

    for symbol in symbols:
        df = raw[symbol].copy()
        df = df.reset_index()

        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

        df["symbol"] = symbol

        expected_cols = ["date", "open", "high", "low", "close", "volume", "symbol"]
        df = df[expected_cols]

        frames.append(df)

    data = pd.concat(frames, ignore_index=True)

    data["date"] = pd.to_datetime(data["date"]).dt.date
    data = data.sort_values(["symbol", "date"]).reset_index(drop=True)

    print(f"Downloaded {len(data):,} rows.", flush=True)

    return data


def clean_data(data):
    """
    Basic data cleaning.
    Removes bad rows, missing prices, and impossible values.
    """

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
    """
    Adds the other ETF close price as a feature.

    For TQQQ rows:
        other_symbol_close = SQQQ close

    For SQQQ rows:
        other_symbol_close = TQQQ close
    """

    print("Adding cross-symbol features...", flush=True)

    wide_close = data.pivot(index="date", columns="symbol", values="close").reset_index()

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

    return data


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(data):
    """
    Creates lag features, moving averages, and future target columns.
    """

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

        df["other_symbol_return"] = df["other_symbol_close"].pct_change()

        for horizon in HORIZONS:
            df[f"actual_{horizon}d"] = df["close"].shift(-horizon)

            df[f"target_return_{horizon}d"] = (
                df[f"actual_{horizon}d"] - df["close"]
            ) / df["close"]

            # 1 means future close is lower than today's close.
            # 0 means no loss.
            df[f"target_loss_{horizon}d"] = np.where(
                df[f"actual_{horizon}d"] < df["close"],
                1,
                0,
            )

        feature_frames.append(df)

    features = pd.concat(feature_frames, ignore_index=True)
    features = features.sort_values(["symbol", "date"]).reset_index(drop=True)

    print(f"Feature dataset has {len(features):,} rows.", flush=True)

    return features


def get_feature_columns(df):
    """
    Selects numeric feature columns used by the model.
    Excludes date, symbol, actuals, and targets.
    """

    excluded_cols = [
        "date",
        "symbol",
    ]

    target_cols = []

    for horizon in HORIZONS:
        target_cols.append(f"actual_{horizon}d")
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
    Trains two models for one horizon:

    1. RandomForestRegressor:
       Predicts future price.

    2. RandomForestClassifier:
       Predicts probability of loss.
    """

    target_price_col = f"actual_{horizon}d"
    target_loss_col = f"target_loss_{horizon}d"

    train_df = train_df.dropna(subset=feature_cols + [target_price_col, target_loss_col])

    if len(train_df) < 100:
        return None, None

    X_train = train_df[feature_cols]
    y_price = train_df[target_price_col]
    y_loss = train_df[target_loss_col]

    price_model = RandomForestRegressor(
        n_estimators=model_params["n_estimators"],
        max_depth=model_params["max_depth"],
        min_samples_leaf=model_params["min_samples_leaf"],
        random_state=model_params["random_state"],
        n_jobs=-1,
    )

    price_model.fit(X_train, y_price)

    loss_model = RandomForestClassifier(
        n_estimators=model_params["n_estimators"],
        max_depth=model_params["max_depth"],
        min_samples_leaf=model_params["min_samples_leaf"],
        random_state=model_params["random_state"],
        n_jobs=-1,
        class_weight="balanced",
    )

    if y_loss.nunique() >= 2:
        loss_model.fit(X_train, y_loss)
    else:
        loss_model = None

    return price_model, loss_model


def predict_one_row(price_model, loss_model, row, feature_cols):
    """
    Makes one prediction for one stock and one horizon.
    """

    X = row[feature_cols]

    prediction = float(price_model.predict(X)[0])

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

    return prediction, confidence_no_loss, loss_probability


# ============================================================
# BACKTESTING
# ============================================================

def run_backtest(features, model_params, output_path):
    """
    Runs one backtest for one parameter combination.

    For every trading day in the backtest period:
    - Train on trailing 12 months
    - Predict 5, 7, 14, and 28 trading days ahead
    - Compare prediction to actual future close
    - Append each successful result row to CSV immediately
    """

    print(f"\nRunning backtest: {model_params['backtest_name']}", flush=True)

    results = []

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])

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
            print("SMOKE_TEST enabled: only testing first 3 dates per symbol.", flush=True)
            test_dates = test_dates[:3]

        for test_date in test_dates:
            test_date = pd.to_datetime(test_date)

            print(
                f"  Testing date: {test_date.date()} | "
                f"backtest={model_params['backtest_name']} | "
                f"symbol={symbol}",
                flush=True,
            )

            training_end_date = test_date - timedelta(days=1)
            training_start_date = test_date - timedelta(days=365)

            train_df = symbol_df[
                (symbol_df["date"] >= training_start_date)
                & (symbol_df["date"] <= training_end_date)
            ].copy()

            test_row = symbol_df[symbol_df["date"] == test_date].copy()

            if test_row.empty:
                print("    Skipped: empty test row.", flush=True)
                continue

            if test_row[feature_cols].isna().any(axis=None):
                print("    Skipped: test row has missing feature values.", flush=True)
                continue

            output_row = {
                "backtest_name": model_params["backtest_name"],
                "n_estimators": model_params["n_estimators"],
                "max_depth": model_params["max_depth"],
                "min_samples_leaf": model_params["min_samples_leaf"],
                "random_state": model_params["random_state"],
                "symbol": symbol,
                "training_start_date": training_start_date.date(),
                "training_end_date": training_end_date.date(),
                "test_start_date": test_date.date(),
                "test_end_date": None,
            }

            max_test_end_date = None

            for horizon in HORIZONS:
                actual_col = f"actual_{horizon}d"

                if pd.isna(test_row.iloc[0][actual_col]):
                    print(f"    Skipped horizon {horizon}d: no actual available.", flush=True)
                    continue

                price_model, loss_model = train_models(
                    train_df=train_df,
                    feature_cols=feature_cols,
                    horizon=horizon,
                    model_params=model_params,
                )

                if price_model is None:
                    print(f"    Skipped horizon {horizon}d: not enough training rows.", flush=True)
                    continue

                prediction, confidence_no_loss, loss_probability = predict_one_row(
                    price_model=price_model,
                    loss_model=loss_model,
                    row=test_row,
                    feature_cols=feature_cols,
                )

                actual = float(test_row.iloc[0][actual_col])
                current_close = float(test_row.iloc[0]["close"])

                actual_minus_prediction = actual - prediction
                prediction_too_high = int(actual_minus_prediction < 0)

                future_row_index = test_row.index[0] + horizon

                if future_row_index < len(symbol_df):
                    horizon_end_date = symbol_df.iloc[future_row_index]["date"].date()

                    if max_test_end_date is None:
                        max_test_end_date = horizon_end_date
                    else:
                        max_test_end_date = max(max_test_end_date, horizon_end_date)

                output_row[f"{horizon}d_prediction"] = prediction
                output_row[f"{horizon}d_actual"] = actual
                output_row[f"{horizon}d_actual_minus_prediction"] = actual_minus_prediction
                output_row[f"{horizon}d_prediction_too_high"] = prediction_too_high
                output_row[f"{horizon}d_confidence_no_loss"] = confidence_no_loss
                output_row[f"{horizon}d_loss_probability"] = loss_probability
                output_row[f"{horizon}d_current_close"] = current_close

            output_row["test_end_date"] = max_test_end_date

            required_prediction_cols = [f"{h}d_prediction" for h in HORIZONS]

            if all(col in output_row for col in required_prediction_cols):
                results.append(output_row)
                append_row_to_csv(output_row, output_path)

                print(
                    f"    Appended result | "
                    f"{model_params['backtest_name']} | "
                    f"{symbol} | "
                    f"{test_date.date()}",
                    flush=True,
                )
            else:
                print("    Skipped row: not all horizons produced predictions.", flush=True)

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
    """
    Runs the backtest once per hyperparameter combination.
    Appends each individual result row to the CSV as it goes.
    """

    if os.path.exists(BACKTEST_OUTPUT_PATH):
        os.remove(BACKTEST_OUTPUT_PATH)
        print(f"Removed old file: {BACKTEST_OUTPUT_PATH}", flush=True)

    parameter_grid = PARAMETER_GRID

    if SMOKE_TEST:
        print("SMOKE_TEST enabled: using only first parameter combination.", flush=True)
        parameter_grid = PARAMETER_GRID[:1]

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
    """
    Prints simple backtest diagnostics by backtest_name, symbol, and horizon.
    """

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
                pred_col = f"{horizon}d_prediction"
                actual_col = f"{horizon}d_actual"
                residual_col = f"{horizon}d_actual_minus_prediction"
                bad_col = f"{horizon}d_prediction_too_high"

                if pred_col not in symbol_df.columns:
                    continue

                valid = symbol_df.dropna(subset=[pred_col, actual_col])

                if valid.empty:
                    continue

                mae = mean_absolute_error(valid[actual_col], valid[pred_col])
                rmse = np.sqrt(mean_squared_error(valid[actual_col], valid[pred_col]))
                pct_actual_above_prediction = 1 - valid[bad_col].mean()
                avg_residual = valid[residual_col].mean()

                print(
                    f"    {horizon}d | "
                    f"MAE={mae:.4f} | "
                    f"RMSE={rmse:.4f} | "
                    f"% actual >= prediction={pct_actual_above_prediction:.2%} | "
                    f"avg actual-prediction={avg_residual:.4f}",
                    flush=True,
                )


# ============================================================
# PRODUCTION FORECAST
# ============================================================

def run_production_forecast(features):
    """
    Production forecast.

    For each symbol:
    - Use the latest available trading day
    - Train on trailing 12 months
    - Predict 5, 7, 14, and 28 trading days ahead
    """

    print("\nRunning production forecast...", flush=True)

    results = []

    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])

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

        latest_date = latest_row.iloc[0]["date"]
        training_end_date = latest_date - timedelta(days=1)
        training_start_date = latest_date - timedelta(days=365)

        train_df = symbol_df[
            (symbol_df["date"] >= training_start_date)
            & (symbol_df["date"] <= training_end_date)
        ].copy()

        output_row = {
            "forecast_date": forecast_date,
            "data_as_of_date": latest_date.date(),
            "stock_symbol": symbol,
            "stock_start_value": float(latest_row.iloc[0]["open"]),
            "stock_end_value": float(latest_row.iloc[0]["close"]),
            "training_start_date": training_start_date.date(),
            "training_end_date": training_end_date.date(),
            "production_model_name": model_params["backtest_name"],
            "n_estimators": model_params["n_estimators"],
            "max_depth": model_params["max_depth"],
            "min_samples_leaf": model_params["min_samples_leaf"],
            "random_state": model_params["random_state"],
        }

        for horizon in HORIZONS:
            price_model, loss_model = train_models(
                train_df=train_df,
                feature_cols=feature_cols,
                horizon=horizon,
                model_params=model_params,
            )

            if price_model is None:
                output_row[f"{horizon}d_prediction"] = np.nan
                output_row[f"{horizon}d_confidence_no_loss"] = np.nan
                output_row[f"{horizon}d_loss_probability"] = np.nan
                continue

            prediction, confidence_no_loss, loss_probability = predict_one_row(
                price_model=price_model,
                loss_model=loss_model,
                row=latest_row,
                feature_cols=feature_cols,
            )

            output_row[f"{horizon}d_prediction"] = prediction
            output_row[f"{horizon}d_confidence_no_loss"] = confidence_no_loss
            output_row[f"{horizon}d_loss_probability"] = loss_probability

        results.append(output_row)

    production_forecast = pd.DataFrame(results)

    print(f"Production forecast created {len(production_forecast):,} rows.", flush=True)

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

    production_forecast = run_production_forecast(features)
    production_forecast.to_csv(PRODUCTION_OUTPUT_PATH, index=False)

    print(f"\nSaved backtest results to: {BACKTEST_OUTPUT_PATH}", flush=True)
    print(f"Saved production forecast to: {PRODUCTION_OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
