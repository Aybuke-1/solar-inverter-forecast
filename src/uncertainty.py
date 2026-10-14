"""Santral toplam güç tahmini için doğrulama hatalarından aralık üret."""

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TARGET_COVERAGE = 0.80
MIN_GROUP_POINTS = 20


def aggregate_plant(rows: pd.DataFrame, inverter_count: int) -> pd.DataFrame:
    """Aynı saatteki tam 22 inverter kaydını tek santral ölçümüne çevir."""
    plant = rows.groupby("DATE_TIME", as_index=False).agg(
        TARGET_TIME=("TARGET_TIME", "first"),
        AC_POWER=("AC_POWER", "sum"),
        NEXT_AC_POWER=("NEXT_AC_POWER", "sum"),
        MODEL_PREDICTION=("MODEL_PREDICTION", "sum"),
        IRRADIATION=("IRRADIATION", "first"),
        inverter_count=("SOURCE_KEY", "nunique"),
    )
    return plant[plant["inverter_count"] == inverter_count].sort_values("DATE_TIME")


def fit_error_band(validation: pd.DataFrame) -> dict:
    """Doğrulama dönemindeki hataları mevcut güç düzeyine göre grupla."""
    positive = validation.loc[validation["AC_POWER"] > 0, "AC_POWER"]
    edges = np.unique(np.quantile(positive, [0.25, 0.50, 0.75])).tolist()
    bins = np.where(validation["AC_POWER"] <= 0, 0,
                    np.searchsorted(edges, validation["AC_POWER"], side="right") + 1)
    errors = (validation["NEXT_AC_POWER"] - validation["MODEL_PREDICTION"]).abs().to_numpy()
    fallback = float(np.quantile(errors, TARGET_COVERAGE, method="higher"))
    widths = []
    counts = []
    for index in range(len(edges) + 2):
        group = errors[bins == index]
        counts.append(int(len(group)))
        widths.append(float(np.quantile(group, TARGET_COVERAGE, method="higher"))
                      if len(group) >= MIN_GROUP_POINTS else fallback)
    return {"edges": edges, "widths": widths, "counts": counts,
            "target_coverage": TARGET_COVERAGE}


def interval_for_point(band: dict, current_power, point) -> tuple[np.ndarray, np.ndarray]:
    """O andaki toplam güç için geçmişte görülen hata genişliğini kullan."""
    power = np.atleast_1d(np.asarray(current_power, dtype=float))
    prediction = np.atleast_1d(np.asarray(point, dtype=float))
    bins = np.where(power <= 0, 0, np.searchsorted(band["edges"], power, side="right") + 1)
    widths = np.asarray(band["widths"])[bins]
    return np.maximum(prediction - widths, 0), prediction + widths


def build_uncertainty(
    validation_with_predictions: pd.DataFrame,
    test: pd.DataFrame,
    plant_totals: pd.DataFrame,
    project_dir: Path,
) -> dict:
    """Yalnızca doğrulamayla genişlik seç; ayrılmış son testte doğruluğu ölç."""
    inverter_count = int(validation_with_predictions["SOURCE_KEY"].nunique())
    calibration = aggregate_plant(validation_with_predictions, inverter_count)
    test_with_predictions = test[[
        "DATE_TIME", "TARGET_TIME", "SOURCE_KEY", "AC_POWER", "NEXT_AC_POWER", "IRRADIATION",
        "MODEL_PREDICTION",
    ]]
    held_out = aggregate_plant(test_with_predictions, inverter_count)
    if calibration.empty or held_out.empty or len(held_out) != len(plant_totals):
        raise ValueError("Aralık hesabında doğrulama veya tam filo test kayıtları eksik.")
    band = fit_error_band(calibration)
    lower, upper = interval_for_point(band, held_out["AC_POWER"], held_out["MODEL_PREDICTION"])
    results = held_out[[
        "TARGET_TIME", "AC_POWER", "NEXT_AC_POWER", "MODEL_PREDICTION", "IRRADIATION",
    ]].copy()
    results["LOWER_BOUND"] = lower
    results["UPPER_BOUND"] = upper
    results["COVERED"] = (
        (results["NEXT_AC_POWER"] >= results["LOWER_BOUND"])
        & (results["NEXT_AC_POWER"] <= results["UPPER_BOUND"])
    )
    indexed = results.set_index("TARGET_TIME")
    plant_totals["LOWER_BOUND"] = plant_totals["TARGET_TIME"].map(indexed["LOWER_BOUND"])
    plant_totals["UPPER_BOUND"] = plant_totals["TARGET_TIME"].map(indexed["UPPER_BOUND"])
    if plant_totals[["LOWER_BOUND", "UPPER_BOUND"]].isna().any().any():
        raise ValueError("Bazı santral tahminlerine aralık atanamadı.")

    daytime = results[results["IRRADIATION"] > 0]
    metrics = {
        "interval_target_coverage": TARGET_COVERAGE,
        "interval_test_coverage": float(results["COVERED"].mean()),
        "interval_daytime_coverage": float(daytime["COVERED"].mean()),
        "interval_test_points": int(len(results)),
        "interval_daytime_points": int(len(daytime)),
        "interval_mean_width": float((results["UPPER_BOUND"] - results["LOWER_BOUND"]).mean()),
        "interval_daytime_mean_width": float((daytime["UPPER_BOUND"] - daytime["LOWER_BOUND"]).mean()),
        "interval_validation_groups": band["counts"],
    }
    report_dir = project_dir / "reports"
    results.to_csv(report_dir / "plant_prediction_intervals.csv", index=False, float_format="%.2f")
    (report_dir / "interval_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    model_dir = project_dir / "models"
    model_dir.mkdir(exist_ok=True)
    joblib.dump(band, model_dir / "plant_interval_bundle.joblib")
    save_interval_chart(results, report_dir / "figures" / "plant_interval_last_day.png")
    return metrics


def save_interval_chart(results: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    day = results["TARGET_TIME"].dt.date.max()
    rows = results[results["TARGET_TIME"].dt.date == day]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.fill_between(rows["TARGET_TIME"], rows["LOWER_BOUND"], rows["UPPER_BOUND"],
                    color="#f3bd76", alpha=0.32, label="Tahmin aralığı")
    ax.plot(rows["TARGET_TIME"], rows["MODEL_PREDICTION"], color="#d47a20", label="Model tahmini")
    ax.plot(rows["TARGET_TIME"], rows["NEXT_AC_POWER"], color="#2473b9", label="Gerçek güç")
    ax.set_title(f"Santral toplam AC güç tahmini ve aralığı · {day}")
    ax.set_ylabel("Toplam AC güç (veri seti ölçeği)")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
