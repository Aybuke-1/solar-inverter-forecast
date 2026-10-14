const $ = (id) => document.getElementById(id);
const number = (value) => new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(value);
const hour = (stamp) => stamp ? stamp.slice(11, 16) : "—";

async function api(path, body) {
  const response = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Sunucu yanıt vermedi.");
  return data;
}

async function control(action, extra = {}) {
  try {
    await api("/api/control", { action, ...extra });
    await refresh();
  } catch (error) {
    $("connection-state").textContent = `İşlem başarısız: ${error.message}`;
  }
}

function svgElement(name, attrs) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  return element;
}

function renderChart(history, current) {
  const svg = $("live-chart");
  svg.replaceChildren();
  const points = history.map((row) => ({
    time: row.time, actual: row.actual, forecast: row.revealed_forecast,
  }));
  if (current) points.push({ time: current.target_time, actual: null, forecast: null });
  if (!points.length) {
    const label = svgElement("text", { x: 450, y: 130, fill: "#9bb0c5", "text-anchor": "middle" });
    label.textContent = "İlk ölçüm geldiğinde grafik çizilecek";
    svg.append(label);
    return;
  }
  const top = Math.max(1, current?.forecast ?? 0, ...points.flatMap((point) => [point.actual, point.forecast].filter((value) => value !== null))) * 1.12;
  const left = 52, right = 865, bottom = 217, chartTop = 22;
  const x = (index) => left + index * (right - left) / Math.max(points.length - 1, 1);
  const y = (value) => bottom - value / top * (bottom - chartTop);
  for (let i = 0; i <= 3; i++) {
    const value = top * i / 3, yy = y(value);
    svg.append(svgElement("line", { x1: left, x2: right, y1: yy, y2: yy, stroke: "#26394e" }));
    const label = svgElement("text", { x: 44, y: yy + 4, fill: "#9bb0c5", "text-anchor": "end", "font-size": 11 });
    label.textContent = number(value);
    svg.append(label);
  }
  for (const [key, color] of [["actual", "#77adff"], ["forecast", "#ffb15b"]]) {
    let run = [];
    for (let i = 0; i <= points.length; i++) {
      const value = i < points.length ? points[i][key] : null;
      if (value !== null) run.push(`${x(i)},${y(value)}`);
      else {
        if (run.length > 1) svg.append(svgElement("polyline", {
          points: run.join(" "), fill: "none", stroke: color, "stroke-width": 2.5,
          "stroke-linecap": "round", "stroke-linejoin": "round",
        }));
        run = [];
      }
    }
  }
  if (current && points.length > 1) {
    const i = points.length - 1;
    svg.append(svgElement("line", {
      x1: x(i - 1), y1: y(points[i - 1].actual),
      x2: x(i), y2: y(current.forecast), stroke: "#ffb15b",
      "stroke-width": 2.5, "stroke-dasharray": "6 5",
    }));
    svg.append(svgElement("circle", { cx: x(i), cy: y(current.forecast), r: 5, fill: "#ffb15b" }));
  }
  const first = svgElement("text", { x: left, y: 248, fill: "#9bb0c5", "font-size": 12 });
  first.textContent = hour(points[0].time);
  const last = svgElement("text", { x: right, y: 248, fill: "#9bb0c5", "font-size": 12, "text-anchor": "end" });
  last.textContent = hour(points.at(-1).time);
  svg.append(first, last);
}

function render(state) {
  const { current, revealed, replay, history, events } = state;
  $("start-button").textContent = replay.playing ? "Ⅱ Duraklat" : "▶ Akışı başlat";
  $("start-button").disabled = replay.sent === replay.total && !replay.playing;
  $("step-button").disabled = replay.sent === replay.total;
  $("progress-text").textContent = `${replay.sent} / ${replay.total} ölçüm paketi işlendi${replay.playing ? " · akış sürüyor" : ""}`;
  $("progress-fill").style.width = `${100 * replay.sent / Math.max(replay.total, 1)}%`;
  $("connection-state").textContent = "Yerel sunucu bağlı · veriler bu bilgisayarda işleniyor";
  $("current-time").textContent = current ? hour(current.time) : "—";
  $("current-meta").textContent = current ? `${current.inverter_count} inverter · ${current.source === "historical-replay" ? "kayıt oynatımı" : "cihaz ağ geçidi"}` : "Henüz mesaj yok";
  $("current-power").textContent = current ? number(current.power) : "—";
  $("irradiation").textContent = current ? `Işınım: ${current.irradiation.toFixed(3)}` : "Işınım: —";
  $("forecast-power").textContent = current ? number(current.forecast) : "—";
  $("target-time").textContent = current ? `Hedef: ${hour(current.target_time)}` : "Hedef: —";
  $("actual-power").textContent = revealed ? number(revealed.actual) : "—";
  $("previous-error").textContent = revealed ? `${hour(revealed.time)} · mutlak hata: ${number(revealed.error)}` : "Sonraki mesaj bekleniyor";
  $("risk-count").textContent = current && current.risk_examined ? `${current.risk_count} / ${current.risk_examined}` : "—";
  $("risk-description").textContent = current && current.risk_examined
    ? `Gündüz incelenen ${current.risk_examined} inverterin ${current.risk_count} tanesinde ani düşüş uyarısı var.`
    : "Ardışık gündüz ölçümü gelince risk modeli çalışır.";
  $("deviation-state").textContent = revealed ? (revealed.alert ? "İncele" : "Normal") : "—";
  $("deviation-description").textContent = revealed
    ? `${hour(revealed.time)} ölçümü geldi; fark ${number(revealed.error)}. ${revealed.alert ? "Eşik aşıldı." : "Eşik aşılmadı."}`
    : "Gerçek ölçüm gelince tahminle farkı hesaplanır.";
  $("event-count").textContent = `Görülen olay: ${events.length}`;
  const list = $("live-events");
  list.replaceChildren();
  if (!events.length) list.textContent = "Henüz olay yok.";
  for (const event of [...events].reverse().slice(0, 8)) {
    const item = document.createElement("div");
    item.className = "live-event";
    const time = document.createElement("strong");
    time.textContent = hour(event.time);
    const detail = document.createElement("span");
    detail.textContent = `${event.message} · fark ${number(event.error)}`;
    item.append(time, detail);
    list.append(item);
  }
  renderChart(history, current);
}

async function refresh() {
  try {
    render(await api("/api/state"));
  } catch (error) {
    $("connection-state").textContent = `Bağlantı yok: ${error.message}. Sayfayı yerel sunucu adresinden aç.`;
  }
}

$("start-button").addEventListener("click", async () => {
  try {
    const state = await api("/api/state");
    await control(state.replay.playing ? "pause" : "start");
  } catch (error) {
    $("connection-state").textContent = error.message;
  }
});
$("step-button").addEventListener("click", () => control("step"));
$("reset-button").addEventListener("click", () => control("reset"));
$("speed-select").addEventListener("change", (event) => control("speed", { interval_ms: Number(event.target.value) }));
refresh();
setInterval(refresh, 500);
