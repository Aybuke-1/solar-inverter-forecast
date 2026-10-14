"""İlk adım: iki CSV dosyasının temel yapısını göster."""

from pathlib import Path

import pandas as pd


# Bu dosyanın bulunduğu klasörden proje köküne, oradan ham veriye gideriz.
data_dir = Path(__file__).resolve().parents[1] / "data" / "raw"

generation = pd.read_csv(data_dir / "Plant_1_Generation_Data.csv")
weather = pd.read_csv(data_dir / "Plant_1_Weather_Sensor_Data.csv")
generation["DATE_TIME"] = pd.to_datetime(generation["DATE_TIME"], format="%d-%m-%Y %H:%M")
weather["DATE_TIME"] = pd.to_datetime(weather["DATE_TIME"], format="%Y-%m-%d %H:%M:%S")
print("Date types:", generation["DATE_TIME"].dtype, weather["DATE_TIME"].dtype)

print("Generation rows:", len(generation))
print("Weather rows:", len(weather))
print("Inverter count:", generation["SOURCE_KEY"].nunique())

print("\nFirst 3 generation rows:")
print(generation.head(3).to_string(index=False))

print("\nFirst 3 weather rows:")
print(weather.head(3).to_string(index=False))

daytime = generation[generation["AC_POWER"] > 0]
print("\nFirst 3 rows with power production:")
print(daytime.head(3).to_string(index=False))


inverter_id = "bvBOhCH3iADSZry"
inverter = generation[generation["SOURCE_KEY"] == inverter_id]

combined = inverter.merge(
    weather[["DATE_TIME", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE", "IRRADIATION"]],
    on="DATE_TIME",
    how="inner",
    validate="one_to_one",
)

print("Selected inverter:", inverter_id)
print("Selected inverter rows:", len(inverter))
print("Merged rows:", len(combined))
print("\nFirst 3 matched daytime rows:")
print(
    combined.loc[combined["AC_POWER"] > 0, ["DATE_TIME", "AC_POWER", "IRRADIATION"]]
    .head(3)
    .to_string(index=False)
)

future = combined[["DATE_TIME", "AC_POWER"]].copy()
future["DATE_TIME"] = future["DATE_TIME"] - pd.Timedelta(minutes=15)
future = future.rename(columns={"AC_POWER": "NEXT_AC_POWER"})

dataset = combined.merge(future, on="DATE_TIME", how="inner", validate="one_to_one")

print("Prediction examples:", len(dataset))
print(
    dataset.loc[dataset["AC_POWER"] > 0, ["DATE_TIME", "AC_POWER", "NEXT_AC_POWER"]]
    .head(3)
    .to_string(index=False)
)

dataset = dataset.sort_values("DATE_TIME").reset_index(drop=True)
cut = int(len(dataset) * 0.8)

train = dataset.iloc[:cut]
test = dataset.iloc[cut:]

print("Train rows:", len(train), train["DATE_TIME"].min(), "to", train["DATE_TIME"].max())
print("Test rows:", len(test), test["DATE_TIME"].min(), "to", test["DATE_TIME"].max())

test = test.copy()
test["BASELINE_PRED"] = test["AC_POWER"]
test["ABS_ERROR"] = (test["NEXT_AC_POWER"] - test["BASELINE_PRED"]).abs()

print("Simple guess average error:", round(test["ABS_ERROR"].mean(), 2))

from sklearn.ensemble import RandomForestRegressor

train = train.copy()

for part in (train, test):
    part["HOUR"] = part["DATE_TIME"].dt.hour
    part["MINUTE"] = part["DATE_TIME"].dt.minute

features = [
    "AC_POWER",
    "IRRADIATION",
    "AMBIENT_TEMPERATURE",
    "MODULE_TEMPERATURE",
    "HOUR",
    "MINUTE",
]

model = RandomForestRegressor(
    n_estimators=100,
    min_samples_leaf=3,
    random_state=42,
    n_jobs=-1,
)
model.fit(train[features], train["NEXT_AC_POWER"])

test["MODEL_PRED"] = model.predict(test[features])
model_error = (test["NEXT_AC_POWER"] - test["MODEL_PRED"]).abs().mean()
print("Model average error:", round(model_error, 2))

daytime_test = test[test["IRRADIATION"] > 0]

day_baseline_error = (
    daytime_test["NEXT_AC_POWER"] - daytime_test["BASELINE_PRED"]
).abs().mean()

day_model_error = (
    daytime_test["NEXT_AC_POWER"] - daytime_test["MODEL_PRED"]
).abs().mean()

print("Daytime examples:", len(daytime_test))
print("Daytime simple guess error:", round(day_baseline_error, 2))
print("Daytime model error:", round(day_model_error, 2))

import matplotlib.pyplot as plt

plot_day = test["DATE_TIME"].dt.date.max()
plot_data = test[
    (test["DATE_TIME"].dt.date == plot_day) & (test["IRRADIATION"] > 0)
]
times = plot_data["DATE_TIME"] + pd.Timedelta(minutes=15)

plt.figure(figsize=(11, 4))
plt.plot(times, plot_data["NEXT_AC_POWER"], label="Gerçek üretim", linewidth=2)
plt.plot(times, plot_data["MODEL_PRED"], label="Model tahmini")
plt.plot(times, plot_data["BASELINE_PRED"], label="Basit tahmin", alpha=0.7)

plt.title(f"15 dakika sonrası inverter gücü: {plot_day}")
plt.xlabel("Tahmin edilen ölçümün saati")
plt.ylabel("AC güç")
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()

chart_dir = Path(__file__).resolve().parents[1] / "reports" / "figures"
chart_dir.mkdir(parents=True, exist_ok=True)
plt.savefig(chart_dir / "forecast_last_day.png", dpi=160)
print("Chart saved:", chart_dir / "forecast_last_day.png")