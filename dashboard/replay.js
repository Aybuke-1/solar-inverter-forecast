"use strict";

// Her satır: o andaki toplam güç (baseline), 15 dakika sonrası tahmin (model)
// ve bir sonraki adım gelene kadar gizlenen gerçekleşen güç (actual).
const replayData = window.dashboardData;
const series = replayData.plant_series.filter((row) => row.time >= "07:00");
const numberFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const svgNamespace = "http://www.w3.org/2000/svg";

let step = -1;
let timer = null;

const elements = {
  play: document.getElementById("play-button"),
  next: document.getElementById("next-button"),
  reset: document.getElementById("reset-button"),
  speed: document.getElementById("speed-select"),
  currentTime: document.getElementById("current-time"),
  currentPower: document.getElementById("current-power"),
  forecastLabel: document.getElementById("forecast-label"),
  forecastPower: document.getElementById("forecast-power"),
  targetTime: document.getElementById("target-time"),
  actualPower: document.getElementById("actual-power"),
  previousError: document.getElementById("previous-error"),
  progressText: document.getElementById("progress-text"),
  progressFill: document.getElementById("progress-fill"),
  status: document.getElementById("replay-status"),
  chart: document.getElementById("replay-chart"),
};

function formatPower(value) {
  return numberFormat.format(value);
}

function dateTime(minutesBeforeTarget, targetTime) {
  const [hours, minutes] = targetTime.split(":").map(Number);
  const date = new Date(`${replayData.plant_day}T00:00:00`);
  date.setMinutes(hours * 60 + minutes - minutesBeforeTarget);
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

function svgElement(tag, attributes = {}, text = "") {
  const element = document.createElementNS(svgNamespace, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  if (text) element.textContent = text;
  return element;
}

function drawChart() {
  const chart = elements.chart;
  chart.replaceChildren();
  const left = 63;
  const right = 937;
  const top = 20;
  const bottom = 296;
  const peak = Math.max(...series.map((row) => Math.max(row.actual, row.model))) * 1.12;
  const x = (index) => left + (index / (series.length - 1)) * (right - left);
  const y = (power) => bottom - (power / peak) * (bottom - top);

  for (let tick = 0; tick <= 4; tick += 1) {
    const value = (peak * tick) / 4;
    const position = y(value);
    chart.append(svgElement("line", { x1: left, y1: position, x2: right, y2: position, class: "chart-grid" }));
    chart.append(svgElement("text", { x: left - 10, y: position + 4, "text-anchor": "end", class: "chart-axis" }, formatPower(value)));
  }
  for (const index of [0, Math.floor((series.length - 1) / 4), Math.floor((series.length - 1) / 2), Math.floor(((series.length - 1) * 3) / 4), series.length - 1]) {
    chart.append(svgElement("text", { x: x(index), y: bottom + 28, "text-anchor": "middle", class: "chart-axis" }, series[index].time));
  }

  const forecastLast = Math.min(step, series.length - 1);
  const actualLast = Math.min(step - 1, series.length - 1);
  if (forecastLast >= 0) drawLine("model", forecastLast);
  if (actualLast >= 0) drawLine("actual", actualLast);

  function drawLine(kind, lastIndex) {
    const points = series.slice(0, lastIndex + 1).map((row, index) => `${x(index)},${y(row[kind])}`);
    chart.append(svgElement("polyline", { points: points.join(" "), class: `replay-line ${kind}` }));
    chart.append(svgElement("circle", { cx: x(lastIndex), cy: y(series[lastIndex][kind]), r: 6, class: `replay-point ${kind}` }));
    if (kind === "model" && step < series.length) {
      chart.append(svgElement("line", { x1: x(lastIndex), y1: top, x2: x(lastIndex), y2: bottom, class: "replay-cursor" }));
    }
  }
}

function render() {
  const started = step >= 0;
  const complete = step >= series.length;
  const current = started && !complete ? series[step] : null;
  const previous = step > 0 ? series[Math.min(step - 1, series.length - 1)] : null;

  elements.currentTime.textContent = current ? dateTime(15, current.time) : "—";
  elements.currentPower.textContent = current ? formatPower(current.baseline) : "—";
  elements.forecastLabel.textContent = complete ? "Son tahmin" : "15 dakika sonrası tahmin";
  elements.forecastPower.textContent = current ? formatPower(current.model) : complete ? formatPower(series.at(-1).model) : "—";
  elements.targetTime.textContent = current ? `Hedef saat: ${dateTime(0, current.time)}` : complete ? `Hedef saat: ${dateTime(0, series.at(-1).time)}` : "Hedef saat: —";
  elements.actualPower.textContent = previous ? formatPower(previous.actual) : "—";
  elements.previousError.textContent = previous ? `Mutlak hata: ${decimalFormat.format(Math.abs(previous.actual - previous.model))}` : "Mutlak hata: —";
  elements.progressText.textContent = complete ? `${series.length} tahminin sonucu görüldü · tamamlandı` : started ? `${step + 1} / ${series.length} tahmin gösterildi` : "Başlamaya hazır";
  elements.progressFill.style.width = `${started ? (complete ? 100 : ((step + 1) / series.length) * 100) : 0}%`;
  elements.status.textContent = complete ? "Son tahminin gerçek sonucu da açıldı. Baştan izlemek için Başa dön'e bas." : current ? `${dateTime(15, current.time)} ölçümüyle ${dateTime(0, current.time)} için tahmin yapıldı. Gerçek sonuç sonraki adımda açılacak.` : "Başlat'a basarak ilk tahmini gör.";
  elements.play.textContent = timer ? "Ⅱ Duraklat" : complete ? "↺ Yeniden başlat" : "▶ Başlat";
  elements.next.disabled = complete;
  drawChart();
}

function pause() {
  if (timer) clearInterval(timer);
  timer = null;
  render();
}

function advance() {
  if (step >= series.length) return;
  step += 1;
  if (step === series.length) {
    if (timer) clearInterval(timer);
    timer = null;
  }
  render();
}

function play() {
  if (timer) {
    pause();
    return;
  }
  if (step >= series.length) step = -1;
  advance();
  if (step < series.length) timer = setInterval(advance, Number(elements.speed.value));
  render();
}

elements.play.addEventListener("click", play);
elements.next.addEventListener("click", () => { pause(); advance(); });
elements.reset.addEventListener("click", () => { pause(); step = -1; render(); });
elements.speed.addEventListener("change", () => {
  if (timer) {
    clearInterval(timer);
    timer = setInterval(advance, Number(elements.speed.value));
  }
});

render();
