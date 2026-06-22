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

    # Existing core buy metrics
    output_row[f"{horizon}d_count_pred_positive"] = count_pred_positive
    output_row[f"{horizon}d_count_pred_positive_w_actual_positive"] = (
        count_pred_positive_w_actual_positive
    )
    output_row[f"{horizon}d_buy_profit_pct"] = safe_divide(
        count_pred_positive_w_actual_positive,
        count_pred_positive,
    )

    # Return model ON
    output_row[f"{horizon}d_return_pct_model_on_numerator"] = (
        return_pct_actual if count_pred_positive == 1 else 0.0
    )
    output_row[f"{horizon}d_return_pct_model_on_denominator"] = count_pred_positive
    output_row[f"{horizon}d_return_pct_model_on"] = safe_divide(
        output_row[f"{horizon}d_return_pct_model_on_numerator"],
        output_row[f"{horizon}d_return_pct_model_on_denominator"],
    )

    # Return model OFF / baseline
    output_row[f"{horizon}d_return_pct_model_off_numerator"] = return_pct_actual
    output_row[f"{horizon}d_return_pct_model_off_denominator"] = 1
    output_row[f"{horizon}d_return_pct_model_off"] = safe_divide(
        output_row[f"{horizon}d_return_pct_model_off_numerator"],
        output_row[f"{horizon}d_return_pct_model_off_denominator"],
    )

    # Profitable model ON
    output_row[f"{horizon}d_profitable_model_on_numerator"] = (
        count_pred_positive_w_actual_positive
    )
    output_row[f"{horizon}d_profitable_model_on_denominator"] = count_pred_positive
    output_row[f"{horizon}d_profitable_model_on"] = safe_divide(
        output_row[f"{horizon}d_profitable_model_on_numerator"],
        output_row[f"{horizon}d_profitable_model_on_denominator"],
    )

    # Profitable model OFF / baseline
    output_row[f"{horizon}d_profitable_model_off_numerator"] = actual_positive
    output_row[f"{horizon}d_profitable_model_off_denominator"] = 1
    output_row[f"{horizon}d_profitable_model_off"] = safe_divide(
        output_row[f"{horizon}d_profitable_model_off_numerator"],
        output_row[f"{horizon}d_profitable_model_off_denominator"],
    )

    return output_row


def add_average_success_metrics(output_row, horizons):
    model_on_return_num = 0.0
    model_on_return_den = 0

    model_off_return_num = 0.0
    model_off_return_den = 0

    model_on_profitable_num = 0
    model_on_profitable_den = 0

    model_off_profitable_num = 0
    model_off_profitable_den = 0

    for horizon in horizons:
        model_on_return_num += output_row.get(
            f"{horizon}d_return_pct_model_on_numerator",
            0.0,
        )
        model_on_return_den += output_row.get(
            f"{horizon}d_return_pct_model_on_denominator",
            0,
        )

        model_off_return_num += output_row.get(
            f"{horizon}d_return_pct_model_off_numerator",
            0.0,
        )
        model_off_return_den += output_row.get(
            f"{horizon}d_return_pct_model_off_denominator",
            0,
        )

        model_on_profitable_num += output_row.get(
            f"{horizon}d_profitable_model_on_numerator",
            0,
        )
        model_on_profitable_den += output_row.get(
            f"{horizon}d_profitable_model_on_denominator",
            0,
        )

        model_off_profitable_num += output_row.get(
            f"{horizon}d_profitable_model_off_numerator",
            0,
        )
        model_off_profitable_den += output_row.get(
            f"{horizon}d_profitable_model_off_denominator",
            0,
        )

    output_row["average_return_pct_model_on_numerator"] = model_on_return_num
    output_row["average_return_pct_model_on_denominator"] = model_on_return_den
    output_row["average_return_pct_model_on"] = safe_divide(
        model_on_return_num,
        model_on_return_den,
    )

    output_row["average_return_pct_model_off_numerator"] = model_off_return_num
    output_row["average_return_pct_model_off_denominator"] = model_off_return_den
    output_row["average_return_pct_model_off"] = safe_divide(
        model_off_return_num,
        model_off_return_den,
    )

    output_row["average_profitable_model_on_numerator"] = model_on_profitable_num
    output_row["average_profitable_model_on_denominator"] = model_on_profitable_den
    output_row["average_profitable_model_on"] = safe_divide(
        model_on_profitable_num,
        model_on_profitable_den,
    )

    output_row["average_profitable_model_off_numerator"] = model_off_profitable_num
    output_row["average_profitable_model_off_denominator"] = model_off_profitable_den
    output_row["average_profitable_model_off"] = safe_divide(
        model_off_profitable_num,
        model_off_profitable_den,
    )

    return output_row


def get_success_metric_columns(horizons):
    cols = []

    for horizon in horizons:
        cols += [
            f"{horizon}d_return_pct_model_on_numerator",
            f"{horizon}d_return_pct_model_on_denominator",
            f"{horizon}d_return_pct_model_on",
            f"{horizon}d_return_pct_model_off_numerator",
            f"{horizon}d_return_pct_model_off_denominator",
            f"{horizon}d_return_pct_model_off",
            f"{horizon}d_profitable_model_on_numerator",
            f"{horizon}d_profitable_model_on_denominator",
            f"{horizon}d_profitable_model_on",
            f"{horizon}d_profitable_model_off_numerator",
            f"{horizon}d_profitable_model_off_denominator",
            f"{horizon}d_profitable_model_off",
        ]

    cols += [
        "average_return_pct_model_on_numerator",
        "average_return_pct_model_on_denominator",
        "average_return_pct_model_on",
        "average_return_pct_model_off_numerator",
        "average_return_pct_model_off_denominator",
        "average_return_pct_model_off",
        "average_profitable_model_on_numerator",
        "average_profitable_model_on_denominator",
        "average_profitable_model_on",
        "average_profitable_model_off_numerator",
        "average_profitable_model_off_denominator",
        "average_profitable_model_off",
    ]

    return cols
