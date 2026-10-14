"use strict";

const analysisData = window.dashboardData;
const format = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const integerFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderHourly() {
  const selected = document.getElementById("analysis-inverter").value;
  const showNight = document.getElementById("show-night").checked;
  const source = selected === "all"
    ? analysisData.hourly_errors
    : analysisData.inverter_hourly_errors.filter((row) => row.id === selected);
  const rows = source.filter((row) => showNight || (row.hour >= 6 && row.hour <= 18));
  const maximum = Math.max(1, ...rows.map((row) => Math.max(row.baseline_mae, row.model_mae)));
  const container = document.getElementById("hourly-bars");
  container.replaceChildren();

  for (const row of rows) {
    const wrapper = node("div", "hour-row");
    const hour = node("span", "hour-label", `${String(row.hour).padStart(2, "0")}:00`);
    hour.title = `${integerFormat.format(row.examples)} test örneği`;
    wrapper.append(hour);
    const tracks = node("div", "hour-tracks");
    for (const [name, value] of [["baseline", row.baseline_mae], ["model", row.model_mae]]) {
      const track = node("div", "hour-track");
      const bar = node("div", `hour-bar ${name}`);
      bar.style.width = `${Math.max(0, (value / maximum) * 100)}%`;
      track.append(bar);
      tracks.append(track);
    }
    wrapper.append(tracks);
    const values = node("span", "hour-values", `${format.format(row.baseline_mae)} / ${format.format(row.model_mae)}`);
    values.title = "Basit tahmin MAE / Model MAE";
    if (row.model_mae > row.baseline_mae) values.classList.add("worse");
    wrapper.append(values);
    container.append(wrapper);
  }

  const better = rows.filter((row) => row.model_mae < row.baseline_mae).length;
  const worse = rows.filter((row) => row.model_mae > row.baseline_mae).length;
  const hardest = [...rows].sort((a, b) => b.model_mae - a.model_mae)[0];
  const scope = selected === "all" ? "Tüm inverterlerde" : "Seçilen inverterde";
  document.getElementById("hourly-insight").textContent = `${scope} gösterilen ${rows.length} saatten ${better} tanesinde model, ${worse} tanesinde basit tahmin daha düşük hata verdi. En zor hedef saati ${String(hardest.hour).padStart(2, "0")}:00 (model MAE ${format.format(hardest.model_mae)}).`;
}

function renderImportance() {
  const container = document.getElementById("importance-bars");
  const maximum = Math.max(...analysisData.feature_importance.map((row) => row.mae_increase), 1);
  for (const row of analysisData.feature_importance) {
    const wrapper = node("div", "importance-row");
    wrapper.append(node("span", "importance-label", row.feature));
    const track = node("div", "importance-track");
    const bar = node("div", "importance-fill");
    bar.style.width = `${Math.max(0, (row.mae_increase / maximum) * 100)}%`;
    track.append(bar);
    wrapper.append(track, node("strong", `importance-value${row.mae_increase < 0 ? " negative" : ""}`, `${row.mae_increase >= 0 ? "+" : ""}${format.format(row.mae_increase)}`));
    container.append(wrapper);
  }
}

function initializeAnalysis() {
  if (!analysisData?.hourly_errors || !analysisData?.feature_importance) {
    document.querySelector("main").textContent = "Analiz verisi bulunamadı. Önce src/plant_model.py dosyasını çalıştır.";
    return;
  }
  const metrics = analysisData.metrics;
  const productionHours = analysisData.hourly_errors.filter((row) => row.hour >= 6 && row.hour <= 18);
  const hardest = [...productionHours].sort((a, b) => b.model_mae - a.model_mae)[0];
  document.getElementById("analysis-examples").textContent = integerFormat.format(metrics.test_examples);
  document.getElementById("hardest-hour").textContent = `${String(hardest.hour).padStart(2, "0")}:00`;
  document.getElementById("hardest-error").textContent = `Model MAE ${format.format(hardest.model_mae)}`;
  document.getElementById("feature-count").textContent = String(analysisData.feature_importance.length);
  document.getElementById("alert-threshold").textContent = integerFormat.format(metrics.alert_threshold_p95_validation);
  document.getElementById("alert-summary").textContent = `Bu eşik son testteki ${integerFormat.format(metrics.plant_time_points)} zaman noktasının ${metrics.test_alert_count} tanesinde aşıldı. Simülasyonda oynatılan son günde ${metrics.last_day_alert_count} büyük sapma var.`;
  if (metrics.interval_test_coverage !== undefined) {
    document.getElementById("interval-coverage").textContent = `${Math.round(metrics.interval_test_coverage * 100)}%`;
    document.getElementById("interval-count").textContent = `${integerFormat.format(metrics.interval_test_points)} test noktası`;
    document.getElementById("interval-daytime").textContent = `${Math.round(metrics.interval_daytime_coverage * 100)}%`;
    document.getElementById("interval-daytime-count").textContent = `${integerFormat.format(metrics.interval_daytime_points)} gündüz noktası`;
    document.getElementById("interval-width").textContent = integerFormat.format(metrics.interval_mean_width);
    document.getElementById("interval-reading").textContent = `Doğrulama hatalarından hedeflenen kapsama %${Math.round(metrics.interval_target_coverage * 100)}; son testte gözlenen %${(metrics.interval_test_coverage * 100).toFixed(1).replace(".", ",")}. Gerçekte aralığın tutma oranını test verisi gösterir; hedef oranı garanti saymayız.`;
  }

  const select = document.getElementById("analysis-inverter");
  for (const inverter of analysisData.inverters) {
    const option = node("option", "", inverter.id);
    option.value = inverter.id;
    select.append(option);
  }
  select.addEventListener("change", renderHourly);
  document.getElementById("show-night").addEventListener("change", renderHourly);
  renderHourly();
  renderImportance();
}

initializeAnalysis();
