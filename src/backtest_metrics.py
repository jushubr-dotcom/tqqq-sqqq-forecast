import numpy as np
import pandas as pd


BUY_RETURN_THRESHOLD = 0.0


def safe_divide(numerator, denominator):
    if denominator is None or pd.isna(denominator) or denominator == 0:
        return np.nan
    return numerator / denominator


def add_horizon_success_metrics(
    output_row,
    horizon,
    return_pct_pred,
    return_pct_actual,
    loss_probability=None,
    buy_return_threshold=BUY_RETURN_THRESHOLD,
    model_buy_signal=None,
):
    """
    Adds model ON/OFF success metrics for one horizon.

    Key point:
    - If model_buy_signal is provided, it controls whether the model is ON.
    - If model_buy_signal is not provided, fallback remains old behaviour:
      model ON = return_pct_pred > buy_return_threshold.

    This makes the function backward-compatible with RandomForest, XGBoost,
    LightGBM, CatBoost, Ridge, ElasticNet, etc.
    """

    if model_buy_signal is None:
        count_pred_positive = int(return_pct_pred > buy_return_threshold)
    else:
        count_pred_positive = int(model_buy_signal)

    raw_pred_positive = int(return_pct_pred > buy_return_threshold)
    actual_positive = int(return_pct_actual > 0)

    count_pred_positive_w_actual_positive = int(
        count_pred_positive == 1 and actual_positive == 1
    )

    output_row[f"{horizon}d_raw_pred_positive"] = raw_pred_positive
    output_row[f"{horizon}d_count_pred_positive"] = count_pred_positive
    output_row[f"{horizon}d_count_pred_positive_w_actual_positive"] = (
        count_pred_positive_w_actual_positive
    )
    output_row[f"{horizon}d_buy_profit_pct"] = safe_divide(
        count_pred_positive_w_actual_positive,
        count_pred_positive,
    )

    output_row[f"{horizon}d_return_pct_model_on_numerator"] = (
        return_pct_actual if count_pred_positive == 1 else 0.0
    )
    output_row[f"{horizon}d_return_pct_model_on_denominator"] = count_pred_positive
    output_row[f"{horizon}d_return_pct_model_on"] = safe_divide(
        output_row[f"{horizon}d_return_pct_model_on_numerator"],
        output_row[f"{horizon}d_return_pct_model_on_denominator"],
    )

    output_row[f"{horizon}d_return_pct_model_off_numerator"] = return_pct_actual
    output_row[f"{horizon}d_return_pct_model_off_denominator"] = 1
    output_row[f"{horizon}d_return_pct_model_off"] = return_pct_actual

    output_row[f"{horizon}d_return_pct_model_uplift"] = (
        output_row[f"{horizon}d_return_pct_model_on"]
        - output_row[f"{horizon}d_return_pct_model_off"]
        if count_pred_positive == 1
        else np.nan
    )

    output_row[f"{horizon}d_profitable_model_on_numerator"] = (
        count_pred_positive_w_actual_positive
    )
    output_row[f"{horizon}d_profitable_model_on_denominator"] = count_pred_positive
    output_row[f"{horizon}d_profitable_model_on"] = safe_divide(
        output_row[f"{horizon}d_profitable_model_on_numerator"],
        output_row[f"{horizon}d_profitable_model_on_denominator"],
    )

    output_row[f"{horizon}d_profitable_model_off_numerator"] = actual_positive
    output_row[f"{horizon}d_profitable_model_off_denominator"] = 1
    output_row[f"{horizon}d_profitable_model_off"] = actual_positive

    output_row[f"{horizon}d_profitable_model_uplift"] = (
        output_row[f"{horizon}d_profitable_model_on"]
        - output_row[f"{horizon}d_profitable_model_off"]
        if count_pred_positive == 1
        else np.nan
    )

    output_row[f"{horizon}d_model_on_trade_count"] = count_pred_positive
    output_row[f"{horizon}d_model_on_trade_rate"] = count_pred_positive / 1

    output_row[f"{horizon}d_model_on_total_return"] = (
        return_pct_actual if count_pred_positive == 1 else 0.0
    )

    output_row[f"{horizon}d_model_on_worst_return"] = (
        return_pct_actual if count_pred_positive == 1 else np.nan
    )

    output_row[f"{horizon}d_model_on_median_return"] = (
        return_pct_actual if count_pred_positive == 1 else np.nan
    )

    return output_row


def add_average_success_metrics(output_row, horizons):
    model_on_returns = []
    model_on_return_num = 0.0
    model_on_return_den = 0

    model_off_return_num = 0.0
    model_off_return_den = 0

    model_on_profitable_num = 0
    model_on_profitable_den = 0

    model_off_profitable_num = 0
    model_off_profitable_den = 0

    raw_pred_positive_num = 0

    for horizon in horizons:
        on_den = output_row.get(f"{horizon}d_return_pct_model_on_denominator", 0)
        on_num = output_row.get(f"{horizon}d_return_pct_model_on_numerator", 0.0)

        model_on_return_num += on_num
        model_on_return_den += on_den

        if on_den == 1:
            model_on_returns.append(on_num)

        model_off_return_num += output_row.get(
            f"{horizon}d_return_pct_model_off_numerator", 0.0
        )
        model_off_return_den += output_row.get(
            f"{horizon}d_return_pct_model_off_denominator", 0
        )

        model_on_profitable_num += output_row.get(
            f"{horizon}d_profitable_model_on_numerator", 0
        )
        model_on_profitable_den += output_row.get(
            f"{horizon}d_profitable_model_on_denominator", 0
        )

        model_off_profitable_num += output_row.get(
            f"{horizon}d_profitable_model_off_numerator", 0
        )
        model_off_profitable_den += output_row.get(
            f"{horizon}d_profitable_model_off_denominator", 0
        )

        raw_pred_positive_num += output_row.get(f"{horizon}d_raw_pred_positive", 0)

    output_row["average_raw_pred_positive_count"] = raw_pred_positive_num

    output_row["average_return_pct_model_on_numerator"] = model_on_return_num
    output_row["average_return_pct_model_on_denominator"] = model_on_return_den
    output_row["average_return_pct_model_on"] = safe_divide(
        model_on_return_num, model_on_return_den
    )

    output_row["average_return_pct_model_off_numerator"] = model_off_return_num
    output_row["average_return_pct_model_off_denominator"] = model_off_return_den
    output_row["average_return_pct_model_off"] = safe_divide(
        model_off_return_num, model_off_return_den
    )

    output_row["average_return_pct_model_uplift"] = (
        output_row["average_return_pct_model_on"]
        - output_row["average_return_pct_model_off"]
        if not pd.isna(output_row["average_return_pct_model_on"])
        else np.nan
    )

    output_row["average_profitable_model_on_numerator"] = model_on_profitable_num
    output_row["average_profitable_model_on_denominator"] = model_on_profitable_den
    output_row["average_profitable_model_on"] = safe_divide(
        model_on_profitable_num, model_on_profitable_den
    )

    output_row["average_profitable_model_off_numerator"] = model_off_profitable_num
    output_row["average_profitable_model_off_denominator"] = model_off_profitable_den
    output_row["average_profitable_model_off"] = safe_divide(
        model_off_profitable_num, model_off_profitable_den
    )

    output_row["average_profitable_model_uplift"] = (
        output_row["average_profitable_model_on"]
        - output_row["average_profitable_model_off"]
        if not pd.isna(output_row["average_profitable_model_on"])
        else np.nan
    )

    output_row["average_model_on_trade_count"] = model_on_return_den
    output_row["average_model_on_trade_rate"] = safe_divide(
        model_on_return_den, model_off_return_den
    )

    output_row["average_model_on_total_return"] = model_on_return_num
    output_row["average_model_on_worst_return"] = (
        float(np.min(model_on_returns)) if model_on_returns else np.nan
    )
    output_row["average_model_on_median_return"] = (
        float(np.median(model_on_returns)) if model_on_returns else np.nan
    )

    return output_row


def get_success_metric_columns(horizons):
    cols = []

    for horizon in horizons:
        cols += [
            f"{horizon}d_raw_pred_positive",
            f"{horizon}d_return_pct_model_on_numerator",
            f"{horizon}d_return_pct_model_on_denominator",
            f"{horizon}d_return_pct_model_on",
            f"{horizon}d_return_pct_model_off_numerator",
            f"{horizon}d_return_pct_model_off_denominator",
            f"{horizon}d_return_pct_model_off",
            f"{horizon}d_return_pct_model_uplift",
            f"{horizon}d_profitable_model_on_numerator",
            f"{horizon}d_profitable_model_on_denominator",
            f"{horizon}d_profitable_model_on",
            f"{horizon}d_profitable_model_off_numerator",
            f"{horizon}d_profitable_model_off_denominator",
            f"{horizon}d_profitable_model_off",
            f"{horizon}d_profitable_model_uplift",
            f"{horizon}d_model_on_trade_count",
            f"{horizon}d_model_on_trade_rate",
            f"{horizon}d_model_on_total_return",
            f"{horizon}d_model_on_worst_return",
            f"{horizon}d_model_on_median_return",
        ]

    cols += [
        "average_raw_pred_positive_count",
        "average_return_pct_model_on_numerator",
        "average_return_pct_model_on_denominator",
        "average_return_pct_model_on",
        "average_return_pct_model_off_numerator",
        "average_return_pct_model_off_denominator",
        "average_return_pct_model_off",
        "average_return_pct_model_uplift",
        "average_profitable_model_on_numerator",
        "average_profitable_model_on_denominator",
        "average_profitable_model_on",
        "average_profitable_model_off_numerator",
        "average_profitable_model_off_denominator",
        "average_profitable_model_off",
        "average_profitable_model_uplift",
        "average_model_on_trade_count",
        "average_model_on_trade_rate",
        "average_model_on_total_return",
        "average_model_on_worst_return",
        "average_model_on_median_return",
    ]

    return cols
