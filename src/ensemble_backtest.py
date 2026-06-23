import pandas as pd
import numpy as np


# =========================
# CONFIG
# =========================

INPUT_FILE = "outputs/backtest_results.csv"
OUTPUT_FILE = "outputs/ensemble_backtest_results.csv"

DATE_COL = "date"
MODEL_COL = "model_name"

PRED_COL = "3d_return_pct_pred"
ACTUAL_COL = "3d_return_pct_actual"

# Minimum predicted return for a model to count as ON.
# If your predicted returns are decimals, e.g. 0.006 = 0.6%, use 0.
# If they are percentages, e.g. 0.6 = 0.6%, still use 0.
MODEL_ON_THRESHOLD = 0

# Ensemble rule mode:
# "strict" = best precision, fewer buys
# "score" = slightly more flexible
ENSEMBLE_MODE = "strict"


# =========================
# MODEL GROUPS
# =========================

EXTRATREES_BEST = [
    "et_100trees_depth4_leaf20_log2_6m"
]

ELASTICNET_BEST_BLOCK = [
    "elasticnet_alpha01_l1_05_logreg_C001_6m",
    "elasticnet_alpha01_l1_05_logreg_C005_6m",
    "elasticnet_alpha01_l1_05_logreg_C01_6m",
    "elasticnet_alpha01_l1_09_logreg_C001_6m",
    "elasticnet_alpha1_l1_01_logreg_C001_6m",
    "elasticnet_alpha1_l1_05_logreg_C001_6m",
]

CATBOOST_CONFIRM = [
    "cat_50trees_depth2_lr003_l2_5_6m",
    "cat_100trees_depth3_lr003_l2_5_6m",
]

RANDOMFOREST_CONFIRM = [
    "rf_100trees_depth5_leaf20_sqrt_6m",
    "rf_100trees_depth6_leaf20_sqrt_6m",
    "rf_100trees_depth4_leaf20_log2_6m",
    "rf_100trees_depth4_leaf20_sqrt_6m",
]

XGBOOST_CONFIRM = [
    "xgb_25trees_depth2_lr003_child5_sub08_col08_6m"
]

LIGHTGBM_CONFIRM = [
    "lgbm_100trees_depth2_lr003_leaves3_child40_sub08_col08_6m",
    "lgbm_125trees_depth2_lr004_leaves3_child40_sub08_col08_6m",
]

RIDGE_CONFIRM = [
    "ridge_alpha001_logreg_C001_6m"
]

WEAK_ELASTICNET = [
    "elasticnet_alpha001_l1_01_logreg_C001_6m",
    "elasticnet_alpha001_l1_05_logreg_C001_6m",
]

WEAK_RIDGE = [
    "ridge_alpha1_logreg_C001_6m",
    "ridge_alpha1_logreg_C005_6m",
    "ridge_alpha1_logreg_C01_6m",
    "ridge_alpha10_logreg_C001_6m",
    "ridge_alpha10_logreg_C005_6m",
    "ridge_alpha10_logreg_C01_6m",
    "ridge_alpha100_logreg_C001_6m",
]

WEAK_XGB = [
    "xgb_50trees_depth2_lr003_child5_sub08_col08_6m"
]


# =========================
# HELPERS
# =========================

def any_model_on(row, model_list):
    existing = [m for m in model_list if m in row.index]
    if not existing:
        return False
    return row[existing].fillna(False).astype(bool).any()


def count_models_on(row, model_list):
    existing = [m for m in model_list if m in row.index]
    if not existing:
        return 0
    return int(row[existing].fillna(False).astype(bool).sum())


def calculate_ensemble_score(row):
    extratrees_on = any_model_on(row, EXTRATREES_BEST)
    elasticnet_on = any_model_on(row, ELASTICNET_BEST_BLOCK)
    cat_on = any_model_on(row, CATBOOST_CONFIRM)
    rf_on = any_model_on(row, RANDOMFOREST_CONFIRM)
    xgb_on = any_model_on(row, XGBOOST_CONFIRM)
    lgbm_on = any_model_on(row, LIGHTGBM_CONFIRM)
    ridge_on = any_model_on(row, RIDGE_CONFIRM)

    weak_elasticnet_on = any_model_on(row, WEAK_ELASTICNET)
    weak_ridge_on = any_model_on(row, WEAK_RIDGE)
    weak_xgb_on = any_model_on(row, WEAK_XGB)

    score = 0

    score += 3.0 if extratrees_on else 0
    score += 3.0 if elasticnet_on else 0
    score += 2.0 if cat_on else 0
    score += 2.0 if rf_on else 0
    score += 1.5 if xgb_on else 0
    score += 1.0 if lgbm_on else 0
    score += 1.0 if ridge_on else 0

    score -= 2.0 if weak_elasticnet_on else 0
    score -= 2.0 if weak_ridge_on else 0
    score -= 1.5 if weak_xgb_on else 0

    return score


def strict_ensemble_buy(row):
    extratrees_on = any_model_on(row, EXTRATREES_BEST)
    elasticnet_on = any_model_on(row, ELASTICNET_BEST_BLOCK)

    cat_on = any_model_on(row, CATBOOST_CONFIRM)
    rf_on = any_model_on(row, RANDOMFOREST_CONFIRM)
    xgb_on = any_model_on(row, XGBOOST_CONFIRM)

    weak_count = 0
    weak_count += int(any_model_on(row, WEAK_ELASTICNET))
    weak_count += int(any_model_on(row, WEAK_RIDGE))
    weak_count += int(any_model_on(row, WEAK_XGB))

    confirmation_on = cat_on or rf_on or xgb_on

    return (
        extratrees_on
        and elasticnet_on
        and confirmation_on
        and weak_count < 2
    )


# =========================
# LOAD DATA
# =========================

df = pd.read_csv(INPUT_FILE)

required_cols = [DATE_COL, MODEL_COL, PRED_COL, ACTUAL_COL]
missing_cols = [c for c in required_cols if c not in df.columns]

if missing_cols:
    raise ValueError(f"Missing required columns: {missing_cols}")

df[DATE_COL] = pd.to_datetime(df[DATE_COL])

# Model ON means predicted 3d return is above threshold
df["model_on"] = df[PRED_COL] > MODEL_ON_THRESHOLD

# Actual profitable result
df["actual_profitable"] = df[ACTUAL_COL] > 0


# =========================
# PIVOT MODEL SIGNALS
# =========================

signal_wide = (
    df.pivot_table(
        index=DATE_COL,
        columns=MODEL_COL,
        values="model_on",
        aggfunc="max"
    )
    .fillna(False)
)

actual_by_date = (
    df.groupby(DATE_COL, as_index=True)
      .agg(
          actual_3d_return=(ACTUAL_COL, "mean"),
          actual_profitable=("actual_profitable", "max")
      )
)

ensemble = signal_wide.copy()

ensemble["ensemble_score"] = ensemble.apply(calculate_ensemble_score, axis=1)
ensemble["strict_ensemble_buy"] = ensemble.apply(strict_ensemble_buy, axis=1)

if ENSEMBLE_MODE == "strict":
    ensemble["ensemble_buy"] = ensemble["strict_ensemble_buy"]
elif ENSEMBLE_MODE == "score":
    ensemble["ensemble_buy"] = ensemble["ensemble_score"] >= 8
else:
    raise ValueError("ENSEMBLE_MODE must be either 'strict' or 'score'.")

ensemble = ensemble.join(actual_by_date, how="left")


# =========================
# PERFORMANCE SUMMARY
# =========================

buy_days = ensemble[ensemble["ensemble_buy"] == True]
no_buy_days = ensemble[ensemble["ensemble_buy"] == False]

summary = {
    "ensemble_mode": ENSEMBLE_MODE,
    "total_days": len(ensemble),
    "buy_days": len(buy_days),
    "no_buy_days": len(no_buy_days),
    "buy_rate": len(buy_days) / len(ensemble) if len(ensemble) else np.nan,

    "buy_profitable_days": int(buy_days["actual_profitable"].sum()) if len(buy_days) else 0,
    "buy_profit_pct": buy_days["actual_profitable"].mean() if len(buy_days) else np.nan,
    "no_buy_profit_pct": no_buy_days["actual_profitable"].mean() if len(no_buy_days) else np.nan,

    "avg_return_when_buy": buy_days["actual_3d_return"].mean() if len(buy_days) else np.nan,
    "median_return_when_buy": buy_days["actual_3d_return"].median() if len(buy_days) else np.nan,
    "worst_return_when_buy": buy_days["actual_3d_return"].min() if len(buy_days) else np.nan,
    "best_return_when_buy": buy_days["actual_3d_return"].max() if len(buy_days) else np.nan,

    "avg_return_when_no_buy": no_buy_days["actual_3d_return"].mean() if len(no_buy_days) else np.nan,
    "missed_profitable_days": int(no_buy_days["actual_profitable"].sum()) if len(no_buy_days) else 0,
}

summary_df = pd.DataFrame([summary])


# =========================
# EXTRA DIAGNOSTICS
# =========================

ensemble["position_return"] = np.where(
    ensemble["ensemble_buy"],
    ensemble["actual_3d_return"],
    0
)

ensemble["cumulative_strategy_return"] = ensemble["position_return"].cumsum()
ensemble["cumulative_buy_and_hold_3d_return"] = ensemble["actual_3d_return"].cumsum()

ensemble["equity_curve"] = (1 + ensemble["position_return"]).cumprod()

ensemble["running_peak"] = ensemble["equity_curve"].cummax()
ensemble["drawdown"] = ensemble["equity_curve"] / ensemble["running_peak"] - 1

max_drawdown = ensemble["drawdown"].min()
summary_df["max_drawdown"] = max_drawdown


# =========================
# SAVE OUTPUTS
# =========================

ensemble.reset_index().to_csv(OUTPUT_FILE, index=False)
summary_df.to_csv("outputs/ensemble_summary.csv", index=False)

print("\nENSEMBLE SUMMARY")
print(summary_df.T)

print(f"\nSaved detailed ensemble backtest to: {OUTPUT_FILE}")
print("Saved summary to: outputs/ensemble_summary.csv")
