"""15 dakika sonraki inverter gücünü tahmin et ve basit tahminle karşılaştır."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "raw"
INVERTER_ID = "bvBOhCH3iADSZry"
TARGET = "NEXT_AC_POWER"

# Modelin tahmin anında bildiği ölçümler.
BASE_FEATURES = [
    "AC_POWER",
    "IRRADIATION",
    "AMBIENT_TEMPERATURE",
    "MODULE_TEMPERATURE",
    "HOUR",
    "MINUTE",
]

# Ek bilgiler: 15 ve 30 dakika önceki ölçümler ile son değişim.
TREND_FEATURES = BASE_FEATURES + [
    "AC_15M_AGO",
    "AC_30M_AGO",
    "IRRADIATION_15M_AGO",
    "IRRADIATION_30M_AGO",
    "AC_CHANGE_15M",
    "IRRADIATION_CHANGE_15M",
]


def load_dataset() -> pd.DataFrame:
    """Aynı inverterin geçmişini, hava ölçümlerini ve sonraki gücü eşleştir."""
    generation = pd.read_csv(DATA_DIR / "Plant_1_Generation_Data.csv")
    weather = pd.read_csv(DATA_DIR / "Plant_1_Weather_Sensor_Data.csv")

    generation["DATE_TIME"] = pd.to_datetime(
        generation["DATE_TIME"], format="%d-%m-%Y %H:%M"
    )
    weather["DATE_TIME"] = pd.to_datetime(
        weather["DATE_TIME"], format="%Y-%m-%d %H:%M:%S"
    )

    inverter = generation[generation["SOURCE_KEY"] == INVERTER_ID]
    current = inverter.merge(
        weather[
            ["DATE_TIME", "IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE"]
        ],
        on="DATE_TIME",
        how="inner",
        validate="one_to_one",
    ).sort_values("DATE_TIME")

    # Geçmiş kayıtların tarihini ileri taşıyarak bugünkü satırla eşleştiriyoruz.
    lag_15 = current[["DATE_TIME", "AC_POWER", "IRRADIATION"]].copy()
    lag_15["DATE_TIME"] += pd.Timedelta(minutes=15)
    lag_15 = lag_15.rename(
        columns={"AC_POWER": "AC_15M_AGO", "IRRADIATION": "IRRADIATION_15M_AGO"}
    )

    lag_30 = current[["DATE_TIME", "AC_POWER", "IRRADIATION"]].copy()
    lag_30["DATE_TIME"] += pd.Timedelta(minutes=30)
    lag_30 = lag_30.rename(
        columns={"AC_POWER": "AC_30M_AGO", "IRRADIATION": "IRRADIATION_30M_AGO"}
    )

    # Gelecek gücü yalnızca hedef olarak ekliyoruz; model girdisi olmayacak.
    future = current[["DATE_TIME", "AC_POWER"]].copy()
    future["DATE_TIME"] -= pd.Timedelta(minutes=15)
    future = future.rename(columns={"AC_POWER": TARGET})

    dataset = current.merge(lag_15, on="DATE_TIME", validate="one_to_one")
    dataset = dataset.merge(lag_30, on="DATE_TIME", validate="one_to_one")
    dataset = dataset.merge(future, on="DATE_TIME", validate="one_to_one")
    dataset = dataset.sort_values("DATE_TIME").reset_index(drop=True)

    dataset["AC_CHANGE_15M"] = dataset["AC_POWER"] - dataset["AC_15M_AGO"]
    dataset["IRRADIATION_CHANGE_15M"] = (
        dataset["IRRADIATION"] - dataset["IRRADIATION_15M_AGO"]
    )
    dataset["HOUR"] = dataset["DATE_TIME"].dt.hour
    dataset["MINUTE"] = dataset["DATE_TIME"].dt.minute

    required = TREND_FEATURES + [TARGET]
    if dataset.empty or dataset[required].isna().any().any():
        raise ValueError("Eşleşen kayıt yok veya model için gereken bir ölçüm eksik.")
    return dataset


def make_model() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=100,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )


def save_last_day_chart(test: pd.DataFrame, predictions) -> Path:
    """Son test gününün gerçek değerlerini iki tahminle karşılaştır."""
    chart_data = test[["DATE_TIME", TARGET, "AC_POWER"]].copy()
    chart_data["MODEL_PREDICTION"] = predictions
    chart_data["TARGET_TIME"] = chart_data["DATE_TIME"] + pd.Timedelta(minutes=15)
    last_day = chart_data["TARGET_TIME"].dt.date.max()
    chart_data = chart_data[chart_data["TARGET_TIME"].dt.date == last_day]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(chart_data["TARGET_TIME"], chart_data[TARGET], label="Gerçek güç", linewidth=2)
    ax.plot(
        chart_data["TARGET_TIME"],
        chart_data["MODEL_PREDICTION"],
        label="Model tahmini",
        linewidth=1.8,
    )
    ax.plot(
        chart_data["TARGET_TIME"],
        chart_data["AC_POWER"],
        label="Basit tahmin",
        linewidth=1.5,
        alpha=0.8,
    )
    ax.set_title(f"15 dakika sonraki inverter gücü: {last_day}")
    ax.set_xlabel("Tahmin edilen ölçümün saati")
    ax.set_ylabel("AC_POWER (veri setindeki ölçek)")
    ax.legend()
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()

    output_path = PROJECT_DIR / "reports" / "figures" / "final_test_last_day.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def main() -> None:
    dataset = load_dataset()

    # İlk %60 öğrenme, sonraki %20 doğrulama, son %20 test.
    # Bölümler arasında bir satır bırakmak hedeflerin taşmasını önler.
    train_end = int(len(dataset) * 0.6)
    validation_end = int(len(dataset) * 0.8)
    train = dataset.iloc[:train_end]
    validation = dataset.iloc[train_end + 1 : validation_end]
    test = dataset.iloc[validation_end + 1 :]

    print("Örnek sayısı:", len(dataset))
    print("Öğrenme / doğrulama / test:", len(train), len(validation), len(test))
    print("Doğrulama basit tahmin hatası:", round(mean_absolute_error(validation[TARGET], validation["AC_POWER"]), 2))

    candidates = {"Anlık ölçümler": BASE_FEATURES, "Geçmiş eğilim": TREND_FEATURES}
    validation_errors = {}
    for name, features in candidates.items():
        model = make_model()
        model.fit(train[features], train[TARGET])
        predictions = model.predict(validation[features])
        error = mean_absolute_error(validation[TARGET], predictions)
        validation_errors[name] = error
        print(f"Doğrulama {name} hatası: {error:.2f}")

    best_name = min(validation_errors, key=validation_errors.get)
    best_features = candidates[best_name]
    print("Seçilen model girdileri:", best_name)

    # Model seçildikten sonra öğrenme ve doğrulama verisiyle yeniden eğitiyoruz.
    final_training = pd.concat([train, validation])
    final_model = make_model()
    final_model.fit(final_training[best_features], final_training[TARGET])
    test_predictions = final_model.predict(test[best_features])

    test_baseline_error = mean_absolute_error(test[TARGET], test["AC_POWER"])
    test_model_error = mean_absolute_error(test[TARGET], test_predictions)
    daytime = test["IRRADIATION"] > 0
    daytime_baseline_error = mean_absolute_error(
        test.loc[daytime, TARGET], test.loc[daytime, "AC_POWER"]
    )
    daytime_model_error = mean_absolute_error(
        test.loc[daytime, TARGET], test_predictions[daytime.to_numpy()]
    )

    print("Test basit tahmin hatası:", round(test_baseline_error, 2))
    print("Test model hatası:", round(test_model_error, 2))
    print("Gündüz test basit tahmin hatası:", round(daytime_baseline_error, 2))
    print("Gündüz test model hatası:", round(daytime_model_error, 2))
    print("Son test günü grafiği:", save_last_day_chart(test, test_predictions))


if __name__ == "__main__":
    main()
