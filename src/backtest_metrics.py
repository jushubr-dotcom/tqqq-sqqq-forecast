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
):
    count_pred_positive = int(return_pct_pred > buy_return_threshold)
    actual_positive = int(return_pct_actual > 0)

    count_pred_positive_w_actual_positive = int(
        count_pred_positive == 1 and actual_positive == 1
    )

    output_row[f"{horizon}d_count_pred_positive"] = count_pred_positive
    output_row[f"{horizon}d_count_pred_positive_w_actual_positive"] = (
        count_pred_positive_w_actual_positive
    )
    output_row[f"{horizon}d_buy_profit_pct"] = safe_divide(
        count_pred_positive_w_actual_positive,
        count_pred_positive,
    )

    output_row[f"{horizon}d_return_pct_model_on"] = (
        return_pct_actual if count_pred_positive == 1 else np.nan
    )
    output_row[f"{horizon}d_return_pct_model_off"] = return_pct_actual

    output_row[f"{horizon}d_profitable_model_on"] = (
        count_pred_positive_w_actual_positive
        if count_pred_positive == 1
        else np.nan
    )
    output_row[f"{horizon}d_profitable_model_off"] = actual_positive

    return output_row


def add_average_success_metrics(output_row, horizons):
    model_on_returns = []
    model_off_returns = []
    model_on_profitable = []
    model_off_profitable = []

    for horizon in horizons:
        on_return = output_row.get(f"{horizon}d_return_pct_model_on")
        off_return = output_row.get(f"{horizon}d_return_pct_model_off")
        on_profitable = output_row.get(f"{horizon}d_profitable_model_on")
        off_profitable = output_row.get(f"{horizon}d_profitable_model_off")

        if not pd.isna(on_return):
            model_on_returns.append(on_return)

        if not pd.isna(off_return):
            model_off_returns.append(off_return)

        if not pd.isna(on_profitable):
            model_on_profitable.append(on_profitable)

        if not pd.isna(off_profitable):
            model_off_profitable.append(off_profitable)

    output_row["average_return_pct_model_on"] = (
        float(np.mean(model_on_returns)) if model_on_returns else np.nan
    )
    output_row["average_return_pct_model_off"] = (
        float(np.mean(model_off_returns)) if model_off_returns else np.nan
    )
    output_row["average_profitable_model_on"] = (
        float(np.mean(model_on_profitable)) if model_on_profitable else np.nan
    )
    output_row["average_profitable_model_off"] = (
        float(np.mean(model_off_profitable)) if model_off_profitable else np.nan
    )

    return output_row


def get_success_metric_columns(horizons):
    cols = []

    for horizon in horizons:
        cols += [
            f"{horizon}d_return_pct_model_on",
            f"{horizon}d_return_pct_model_off",
            f"{horizon}d_profitable_model_on",
            f"{horizon}d_profitable_model_off",
        ]

    cols += [
        "average_return_pct_model_on",
        "average_return_pct_model_off",
        "average_profitable_model_on",
        "average_profitable_model_off",
    ]

    return cols
