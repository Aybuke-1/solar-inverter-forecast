"""Plant 1'deki tüm inverterler için 15 dakika sonrası AC gücü tahmin et."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "raw"
REPORT_DIR = PROJECT_DIR / "reports"
FIGURE_DIR = REPORT_DIR / "figures"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"
TARGET = "NEXT_AC_POWER"
INPUTS = [
    "AC_POWER",
    "IRRADIATION",
    "AMBIENT_TEMPERATURE",
    "MODULE_TEMPERATURE",
    "HOUR",
    "MINUTE",
]


def load_dataset() -> pd.DataFrame:
    """Üretimi hava verisiyle ve tam 15 dakika sonraki hedefle eşleştir."""
    generation = pd.read_csv(DATA_DIR / "Plant_1_Generation_Data.csv")
    weather = pd.read_csv(DATA_DIR / "Plant_1_Weather_Sensor_Data.csv")
    generation["DATE_TIME"] = pd.to_datetime(
        generation["DATE_TIME"], format="%d-%m-%Y %H:%M"
    )
    weather["DATE_TIME"] = pd.to_datetime(
        weather["DATE_TIME"], format="%Y-%m-%d %H:%M:%S"
    )

    current = generation[["DATE_TIME", "SOURCE_KEY", "AC_POWER"]].merge(
        weather[
            ["DATE_TIME", "IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE"]
        ],
        on="DATE_TIME",
        how="inner",
        validate="many_to_one",
    )

    future = generation[["DATE_TIME", "SOURCE_KEY", "AC_POWER"]].copy()
    future["DATE_TIME"] -= pd.Timedelta(minutes=15)
    future = future.rename(columns={"AC_POWER": TARGET})

    dataset = current.merge(
        future,
        on=["DATE_TIME", "SOURCE_KEY"],
        how="inner",
        validate="one_to_one",
    )
    dataset["TARGET_TIME"] = dataset["DATE_TIME"] + pd.Timedelta(minutes=15)
    dataset["HOUR"] = dataset["DATE_TIME"].dt.hour
    dataset["MINUTE"] = dataset["DATE_TIME"].dt.minute
    dataset = dataset.sort_values(["DATE_TIME", "SOURCE_KEY"]).reset_index(drop=True)

    if dataset.empty or dataset[INPUTS + [TARGET]].isna().any().any():
        raise ValueError("Eşleşen kayıt yok veya gerekli bir ölçüm eksik.")
    return dataset


def time_split(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Aynı saat tüm inverterlerde aynı bölümde kalsın; sınır aşan hedefleri çıkar."""
    times = dataset["DATE_TIME"].drop_duplicates().sort_values().to_numpy()
    train_boundary = times[int(len(times) * 0.6)]
    test_boundary = times[int(len(times) * 0.8)]

    train = dataset[
        (dataset["DATE_TIME"] < train_boundary)
        & (dataset["TARGET_TIME"] < train_boundary)
    ]
    validation = dataset[
        (dataset["DATE_TIME"] >= train_boundary)
        & (dataset["TARGET_TIME"] < test_boundary)
    ]
    test = dataset[dataset["DATE_TIME"] >= test_boundary].copy()
    return train, validation, test


def candidate_models():
    return {
        "Random Forest": RandomForestRegressor(
            n_estimators=80,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": HistGradientBoostingRegressor(
            max_iter=150,
            max_leaf_nodes=31,
            learning_rate=0.08,
            random_state=42,
        ),
    }


def save_inverter_chart(errors: pd.DataFrame) -> Path:
    """İnverter başına iyileşmeyi göster; sıfırın altı modelin kötüleşmesidir."""
    chart_data = errors.sort_values("mae_improvement")
    colors = ["#d65f5f" if value < 0 else "#3a9d78" for value in chart_data["mae_improvement"]]
    fig, ax = plt.subplots(figsize=(10, 9))
    ax.barh(chart_data["inverter"], chart_data["mae_improvement"], color=colors)
    ax.axvline(0, color="#333333", linewidth=1)
    ax.set_xlabel("Basit tahmin MAE − model MAE (pozitif: model daha iyi)")
    ax.set_ylabel("İnverter kimliği")
    ax.set_title("İnverter bazında 15 dakika sonrası tahmin başarısı")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / "inverter_improvement.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_plant_chart(totals: pd.DataFrame) -> Path:
    """Son test gününde tüm inverterlerin toplam AC gücünü çiz."""
    last_day = totals["TARGET_TIME"].dt.date.max()
    day = totals[totals["TARGET_TIME"].dt.date == last_day]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(day["TARGET_TIME"], day[TARGET], label="Gerçek toplam güç", linewidth=2)
    ax.plot(
        day["TARGET_TIME"],
        day["MODEL_PREDICTION"],
        label="Model tahmini",
        linewidth=1.8,
    )
    ax.plot(
        day["TARGET_TIME"],
        day["BASELINE_PREDICTION"],
        label="Basit tahmin",
        linewidth=1.5,
        alpha=0.8,
    )
    ax.set_title(f"Toplam inverter AC gücü: {last_day} (15 dakika sonrası)")
    ax.set_xlabel("Tahmin edilen ölçümün saati")
    ax.set_ylabel("Toplam AC_POWER (veri setindeki ölçek)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / "plant_power_last_day.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def calculate_hourly_errors(test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Son testte hatanın hedef saate ve invertere göre değişimini ölç."""
    results = test[["SOURCE_KEY", "TARGET_TIME", TARGET]].copy()
    results["hour"] = results["TARGET_TIME"].dt.hour
    results["baseline_error"] = (test[TARGET] - test["BASELINE_PREDICTION"]).abs()
    results["model_error"] = (test[TARGET] - test["MODEL_PREDICTION"]).abs()

    def summarize(group_columns: list[str]) -> pd.DataFrame:
        return (
            results.groupby(group_columns, as_index=False)
            .agg(
                examples=(TARGET, "size"),
                baseline_mae=("baseline_error", "mean"),
                model_mae=("model_error", "mean"),
            )
            .sort_values(group_columns)
        )

    return summarize(["hour"]), summarize(["SOURCE_KEY", "hour"])


def grouped_feature_importance(model, inputs: pd.DataFrame, actual: pd.Series) -> pd.DataFrame:
    """Doğrulama verisinde bir girdi grubunu karıştırıp MAE artışını ölç."""
    groups = {
        "Anlık AC güç": ["AC_POWER"],
        "Güneş ışınımı": ["IRRADIATION"],
        "Ortam sıcaklığı": ["AMBIENT_TEMPERATURE"],
        "Panel sıcaklığı": ["MODULE_TEMPERATURE"],
        "Saat": ["HOUR"],
        "Dakika": ["MINUTE"],
        # Cihaz kimliği one-hot sütunlarının birlikte karıştırılması gerekir.
        "İnverter kimliği": [column for column in inputs if column.startswith("SOURCE_KEY_")],
    }
    base_error = mean_absolute_error(actual, np.maximum(model.predict(inputs), 0))
    rng = np.random.default_rng(42)
    rows = []
    for label, columns in groups.items():
        increases = []
        for _ in range(3):
            permutation = rng.permutation(len(inputs))
            shuffled = inputs.copy()
            shuffled.loc[:, columns] = inputs.iloc[permutation][columns].to_numpy()
            error = mean_absolute_error(actual, np.maximum(model.predict(shuffled), 0))
            increases.append(error - base_error)
        rows.append(
            {
                "feature": label,
                "mae_increase": float(np.mean(increases)),
                "std": float(np.std(increases)),
            }
        )
    return pd.DataFrame(rows).sort_values("mae_increase", ascending=False)


def save_hourly_chart(hourly: pd.DataFrame) -> Path:
    """Üretimin görüldüğü hedef saatlerinde iki yöntemin hatasını karşılaştır."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    hours = hourly[hourly["hour"].between(6, 18)]
    positions = np.arange(len(hours))
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(positions - 0.18, hours["baseline_mae"], 0.36, label="Basit tahmin", color="#3a9d78")
    ax.bar(positions + 0.18, hours["model_mae"], 0.36, label="Model", color="#e79b46")
    ax.set_xticks(positions, [f"{hour:02d}:00" for hour in hours["hour"]], rotation=45)
    ax.set_ylabel("Ortalama mutlak hata (MAE)")
    ax.set_xlabel("Tahmin edilen ölçümün saati")
    ax.set_title("Son testte saatlere göre inverter tahmin hatası")
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path = FIGURE_DIR / "hourly_errors.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_importance_chart(importance: pd.DataFrame) -> Path:
    """Girdi grubu karıştırıldığında doğrulama hatasının nasıl değiştiğini çiz."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    values = importance.sort_values("mae_increase")
    colors = ["#d65f5f" if value < 0 else "#3a9d78" for value in values["mae_increase"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(values["feature"], values["mae_increase"], color=colors)
    ax.axvline(0, color="#333333", linewidth=1)
    ax.set_xlabel("Karıştırınca MAE değişimi (pozitif: model bu girdiden yararlanıyor)")
    ax.set_title("Gündüz doğrulama verisinde girdi gruplarının etkisi")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path = FIGURE_DIR / "feature_importance.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def save_dashboard_data(
    metrics: dict,
    errors: pd.DataFrame,
    totals: pd.DataFrame,
    hourly: pd.DataFrame,
    inverter_hourly: pd.DataFrame,
    importance: pd.DataFrame,
) -> Path:
    """Web ekranına yalnızca özet sonuçları ve son günün toplam güç serisini ver."""
    last_day = totals["TARGET_TIME"].dt.date.max()
    last_day_totals = totals[totals["TARGET_TIME"].dt.date == last_day]
    data = {
        "metrics": metrics,
        "inverters": [
            {
                "id": row.inverter,
                "examples": int(row.test_examples),
                "baseline_mae": round(float(row.baseline_mae), 2),
                "model_mae": round(float(row.model_mae), 2),
                "improvement": round(float(row.mae_improvement), 2),
            }
            for row in errors.itertuples(index=False)
        ],
        "hourly_errors": [
            {
                "hour": int(row.hour),
                "examples": int(row.examples),
                "baseline_mae": round(float(row.baseline_mae), 2),
                "model_mae": round(float(row.model_mae), 2),
            }
            for row in hourly.itertuples(index=False)
        ],
        "inverter_hourly_errors": [
            {
                "id": row.SOURCE_KEY,
                "hour": int(row.hour),
                "examples": int(row.examples),
                "baseline_mae": round(float(row.baseline_mae), 2),
                "model_mae": round(float(row.model_mae), 2),
            }
            for row in inverter_hourly.itertuples(index=False)
        ],
        "feature_importance": [
            {
                "feature": row.feature,
                "mae_increase": round(float(row.mae_increase), 2),
                "std": round(float(row.std), 2),
            }
            for row in importance.itertuples(index=False)
        ],
        "plant_day": str(last_day),
        "plant_series": [
            {
                "time": row.TARGET_TIME.strftime("%H:%M"),
                "actual": round(float(row.NEXT_AC_POWER), 2),
                "model": round(float(row.MODEL_PREDICTION), 2),
                "baseline": round(float(row.BASELINE_PREDICTION), 2),
                "lower": round(float(row.LOWER_BOUND), 2),
                "upper": round(float(row.UPPER_BOUND), 2),
            }
            for row in last_day_totals.itertuples(index=False)
        ],
    }
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    path = DASHBOARD_DIR / "data.js"
    path.write_text(
        "window.dashboardData = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    dataset = load_dataset()
    train, validation, test = time_split(dataset)

    # İnverter kimliğini sayısal sütunlara çevirerek modele hangi cihaz olduğunu bildir.
    features = pd.get_dummies(
        dataset[INPUTS + ["SOURCE_KEY"]], columns=["SOURCE_KEY"], dtype=int
    )

    validation_errors = {}
    validation_predictions = {}
    fitted_candidates = {}
    for name, model in candidate_models().items():
        model.fit(features.loc[train.index], train[TARGET])
        predictions = np.maximum(model.predict(features.loc[validation.index]), 0)
        validation_errors[name] = mean_absolute_error(validation[TARGET], predictions)
        validation_predictions[name] = predictions
        fitted_candidates[name] = model

    selected_name = min(validation_errors, key=validation_errors.get)
    validation_model = fitted_candidates[selected_name]
    validation_with_predictions = validation.copy()
    validation_with_predictions["MODEL_PREDICTION"] = validation_predictions[selected_name]
    validation_totals = validation_with_predictions.groupby("TARGET_TIME", as_index=False)[
        [TARGET, "MODEL_PREDICTION"]
    ].sum()
    # Uyarı eşiği, son teste bakılmadan doğrulamadaki toplam güç hatasından seçilir.
    alert_threshold = float(
        (validation_totals[TARGET] - validation_totals["MODEL_PREDICTION"])
        .abs()
        .quantile(0.95)
    )
    validation_daytime = validation[validation["IRRADIATION"] > 0]
    importance = grouped_feature_importance(
        validation_model,
        features.loc[validation_daytime.index],
        validation_daytime[TARGET],
    )

    selected_model = candidate_models()[selected_name]
    final_training = pd.concat([train, validation])
    selected_model.fit(features.loc[final_training.index], final_training[TARGET])
    model_dir = PROJECT_DIR / "models"
    model_dir.mkdir(exist_ok=True)
    joblib.dump(
        {
            "model": selected_model,
            "columns": features.columns.tolist(),
            "source_keys": sorted(dataset["SOURCE_KEY"].unique().tolist()),
            "selected_name": selected_name,
            "alert_threshold": alert_threshold,
        },
        model_dir / "forecast_bundle.joblib",
    )
    test["MODEL_PREDICTION"] = np.maximum(
        selected_model.predict(features.loc[test.index]), 0
    )
    test["BASELINE_PREDICTION"] = test["AC_POWER"]

    overall_baseline = mean_absolute_error(test[TARGET], test["BASELINE_PREDICTION"])
    overall_model = mean_absolute_error(test[TARGET], test["MODEL_PREDICTION"])
    daytime = test[test["IRRADIATION"] > 0]
    daytime_baseline = mean_absolute_error(daytime[TARGET], daytime["BASELINE_PREDICTION"])
    daytime_model = mean_absolute_error(daytime[TARGET], daytime["MODEL_PREDICTION"])

    # Büyük değişim eşiği öğrenme verisinden gelir; testte yalnızca hata analizi yaparız.
    change_threshold = (train[TARGET] - train["AC_POWER"]).abs().quantile(0.90)
    large_change = test[(test[TARGET] - test["AC_POWER"]).abs() >= change_threshold]
    large_change_baseline = mean_absolute_error(
        large_change[TARGET], large_change["BASELINE_PREDICTION"]
    )
    large_change_model = mean_absolute_error(
        large_change[TARGET], large_change["MODEL_PREDICTION"]
    )

    rows = []
    for inverter, group in test.groupby("SOURCE_KEY"):
        baseline_mae = mean_absolute_error(group[TARGET], group["BASELINE_PREDICTION"])
        model_mae = mean_absolute_error(group[TARGET], group["MODEL_PREDICTION"])
        rows.append(
            {
                "inverter": inverter,
                "test_examples": len(group),
                "baseline_mae": baseline_mae,
                "model_mae": model_mae,
                "mae_improvement": baseline_mae - model_mae,
            }
        )
    inverter_errors = pd.DataFrame(rows).sort_values("inverter")

    # Aynı saatteki inverter güçlerini toplamak, santralin toplam inverter gücünü verir.
    plant_totals = test.groupby("TARGET_TIME", as_index=False)[
        [TARGET, "MODEL_PREDICTION", "BASELINE_PREDICTION"]
    ].sum()
    plant_baseline = mean_absolute_error(
        plant_totals[TARGET], plant_totals["BASELINE_PREDICTION"]
    )
    plant_model = mean_absolute_error(plant_totals[TARGET], plant_totals["MODEL_PREDICTION"])
    plant_totals["ABS_MODEL_ERROR"] = (
        plant_totals[TARGET] - plant_totals["MODEL_PREDICTION"]
    ).abs()
    alert_count = int((plant_totals["ABS_MODEL_ERROR"] > alert_threshold).sum())
    last_day = plant_totals["TARGET_TIME"].dt.date.max()
    last_day_alerts = int(
        (
            plant_totals.loc[
                plant_totals["TARGET_TIME"].dt.date == last_day,
                "ABS_MODEL_ERROR",
            ]
            > alert_threshold
        ).sum()
    )
    hourly_errors, inverter_hourly_errors = calculate_hourly_errors(test)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    errors_path = REPORT_DIR / "inverter_errors.csv"
    inverter_errors.to_csv(errors_path, index=False, float_format="%.2f")
    hourly_path = REPORT_DIR / "hourly_errors.csv"
    hourly_errors.to_csv(hourly_path, index=False, float_format="%.2f")
    inverter_hourly_path = REPORT_DIR / "inverter_hourly_errors.csv"
    inverter_hourly_errors.to_csv(inverter_hourly_path, index=False, float_format="%.2f")
    importance_path = REPORT_DIR / "feature_importance.csv"
    importance.to_csv(importance_path, index=False, float_format="%.2f")
    hourly_chart_path = save_hourly_chart(hourly_errors)
    importance_chart_path = save_importance_chart(importance)
    chart_path = save_inverter_chart(inverter_errors)
    plant_chart_path = save_plant_chart(plant_totals)
    from uncertainty import build_uncertainty

    uncertainty_metrics = build_uncertainty(
        validation_with_predictions, test, plant_totals, PROJECT_DIR
    )
    metrics = {
        "inverters": int(dataset["SOURCE_KEY"].nunique()),
        "examples": int(len(dataset)),
        "train_examples": int(len(train)),
        "validation_examples": int(len(validation)),
        "test_examples": int(len(test)),
        "validation_baseline_mae": float(
            mean_absolute_error(validation[TARGET], validation["AC_POWER"])
        ),
        "validation_model_mae": validation_errors,
        "selected_model": selected_name,
        "test_baseline_mae": float(overall_baseline),
        "test_model_mae": float(overall_model),
        "daytime_test_examples": int(len(daytime)),
        "daytime_baseline_mae": float(daytime_baseline),
        "daytime_model_mae": float(daytime_model),
        "large_change_threshold": float(change_threshold),
        "large_change_test_examples": int(len(large_change)),
        "large_change_baseline_mae": float(large_change_baseline),
        "large_change_model_mae": float(large_change_model),
        "inverters_improved": int((inverter_errors["mae_improvement"] > 0).sum()),
        "plant_time_points": int(len(plant_totals)),
        "plant_total_baseline_mae": float(plant_baseline),
        "plant_total_model_mae": float(plant_model),
        "alert_threshold_p95_validation": alert_threshold,
        "test_alert_count": alert_count,
        "last_day_alert_count": last_day_alerts,
        "feature_importance_validation_daytime_examples": int(len(validation_daytime)),
        **uncertainty_metrics,
    }
    metrics_path = REPORT_DIR / "plant_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    dashboard_data_path = save_dashboard_data(
        metrics,
        inverter_errors,
        plant_totals,
        hourly_errors,
        inverter_hourly_errors,
        importance,
    )

    print("İnverter sayısı:", metrics["inverters"])
    print("Örnek sayısı:", metrics["examples"])
    print("Öğrenme / doğrulama / test:", len(train), len(validation), len(test))
    print("Doğrulama basit tahmin hatası:", round(metrics["validation_baseline_mae"], 2))
    for name, error in validation_errors.items():
        print(f"Doğrulama {name} hatası: {error:.2f}")
    print("Seçilen model:", selected_name)
    print("Test basit tahmin hatası:", round(overall_baseline, 2))
    print("Test model hatası:", round(overall_model, 2))
    print("Gündüz test basit tahmin hatası:", round(daytime_baseline, 2))
    print("Gündüz test model hatası:", round(daytime_model, 2))
    print("Büyük değişim eşiği:", round(change_threshold, 2))
    print("Büyük değişimli test örneği:", len(large_change))
    print("Büyük değişimde basit tahmin hatası:", round(large_change_baseline, 2))
    print("Büyük değişimde model hatası:", round(large_change_model, 2))
    print("Modelin iyileştirdiği inverter sayısı:", metrics["inverters_improved"])
    print("Toplam güç basit tahmin hatası:", round(plant_baseline, 2))
    print("Toplam güç model hatası:", round(plant_model, 2))
    print("Tahmin aralığı son test kapsaması:", round(uncertainty_metrics["interval_test_coverage"] * 100, 1), "%")
    print("Büyük sapma eşiği (doğrulama %95):", round(alert_threshold, 2))
    print("Testte büyük sapma sayısı:", alert_count)
    print("Son günde büyük sapma sayısı:", last_day_alerts)
    print("Gündüz değişken etkisi:", importance_path)
    print("Saat bazında hata:", hourly_path)
    print("İnverter ve saat bazında hata:", inverter_hourly_path)
    print("Saatlik hata grafiği:", hourly_chart_path)
    print("Girdi etkisi grafiği:", importance_chart_path)
    print("İnverter sonuçları:", errors_path)
    print("İnverter grafiği:", chart_path)
    print("Toplam güç grafiği:", plant_chart_path)
    print("Tüm sayısal sonuçlar:", metrics_path)
    print("Web ekranı verisi:", dashboard_data_path)

    # Aynı zaman bölümlerini kullanarak operasyon analizlerini de üret.
    from operations_model import build_operations

    build_operations(dataset, train, validation, test, plant_totals, alert_threshold, PROJECT_DIR)


if __name__ == "__main__":
    main()
