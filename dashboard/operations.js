"use strict";

const operationData = window.operationsData;
const formatNumber = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const formatInteger = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const formatPercent = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 });
let visibleEvents = 6;
let selectedPriorityId = null;

function element(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}

function dateLabel(iso) {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

function renderPeer() {
  const featured = operationData.events.find((event) => event.type === "peer");
  const target = document.getElementById("featured-peer");
  if (featured) {
    target.append(element("span", "status", "İnceleme örneği"));
    target.append(element("strong", "", `${dateLabel(featured.time)} – ${dateLabel(featured.end)}`));
    target.append(element("p", "", `${featured.inverters.length} inverter, ${featured.duration_minutes} dakika boyunca filonun belirgin altında kaldı. İlgili cihazlar: ${featured.inverters.join(", ")}.`));
  }
  const list = document.getElementById("peer-list");
  for (const row of operationData.peer_summary) {
    const item = element("div", `peer-row${row.episodes ? " active" : ""}`);
    item.append(element("code", "", row.id));
    item.append(element("span", "", `${row.low_points} düşük ölçüm`));
    item.append(element("strong", "", row.episodes ? `${row.episodes} uzun olay` : "Uzun olay yok"));
    list.append(item);
  }
}

function renderPriorityChart(points) {
  const svg = document.getElementById("priority-chart");
  svg.replaceChildren();
  if (!points.length) {
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "345"); label.setAttribute("y", "125");
    label.setAttribute("text-anchor", "middle"); label.setAttribute("fill", "#9bb0c5");
    label.textContent = "Bu günde kıyas için yeterli üretim yok";
    svg.append(label);
    return;
  }
  const ns = "http://www.w3.org/2000/svg";
  const add = (tag, attrs) => {
    const item = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, String(value));
    svg.append(item);
    return item;
  };
  const max = Math.max(1.35, ...points.map((row) => row.ratio)) * 1.08;
  const x = (i) => 44 + i * 623 / Math.max(points.length - 1, 1);
  const y = (value) => 205 - value / max * 175;
  for (const level of [0.7, 1]) {
    add("line", { x1: 44, x2: 667, y1: y(level), y2: y(level), stroke: level === 0.7 ? "#ef7b7b" : "#526b80", "stroke-dasharray": "5 5" });
    add("text", { x: 37, y: y(level) + 4, fill: "#9bb0c5", "text-anchor": "end", "font-size": 11 }).textContent = level.toFixed(2).replace(".", ",");
  }
  const path = points.map((row, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(row.ratio).toFixed(1)}`).join(" ");
  add("path", { d: path, fill: "none", stroke: "#77adff", "stroke-width": 2.5, "stroke-linecap": "round", "stroke-linejoin": "round" });
  points.forEach((row, i) => {
    if (row.low) add("circle", { cx: x(i), cy: y(row.ratio), r: 4.5, fill: "#ef7b7b" });
  });
  add("text", { x: 44, y: 235, fill: "#9bb0c5", "font-size": 11 }).textContent = points[0].time;
  add("text", { x: 667, y: 235, fill: "#9bb0c5", "text-anchor": "end", "font-size": 11 }).textContent = points.at(-1).time;
}

function renderPriorityDetail() {
  const row = operationData.priority.find((item) => item.id === selectedPriorityId);
  if (!row) return;
  document.getElementById("priority-select").value = row.id;
  document.querySelectorAll(".priority-row").forEach((item) => item.classList.toggle("active", item.dataset.id === row.id));
  const badge = document.getElementById("priority-status");
  badge.textContent = row.status;
  badge.classList.toggle("negative", row.status === "Öncelikli inceleme");
  document.getElementById("priority-id").textContent = row.id;
  document.getElementById("priority-explanation").textContent = row.minutes
    ? `${row.episodes} uzun ayrışma olayı, toplam ${row.minutes} dakika. En uzunu ${row.longest_minutes} dakika sürdü.`
    : row.low_points ? `${row.low_points} kısa düşük ölçüm var; dört ardışık ölçüm süren olay yok.`
      : "Bu test döneminde belirlenen eşiğin altında ölçüm görülmedi.";
  const facts = document.getElementById("priority-facts");
  facts.replaceChildren();
  for (const [label, value] of [
    ["Düşük / uygun ölçüm", `${row.low_points} / ${row.eligible_points}`],
    ["En düşük filo oranı", row.worst_ratio === null ? "—" : formatNumber.format(row.worst_ratio)],
    ["Modelin test MAE değeri", formatNumber.format(row.model_mae)],
  ]) {
    const item = element("div", "");
    item.append(element("span", "", label), element("strong", "", value));
    facts.append(item);
  }
  const series = operationData.priority_series[row.id];
  document.getElementById("priority-chart-label").textContent = `${series.day} · seçilen inceleme günü`;
  renderPriorityChart(series.points);
}

function renderPriority() {
  if (!operationData.priority?.length) return;
  const list = document.getElementById("priority-list");
  const select = document.getElementById("priority-select");
  for (const row of operationData.priority) {
    const option = element("option", "", row.id);
    option.value = row.id;
    select.append(option);
    const button = element("button", "priority-row");
    button.type = "button";
    button.dataset.id = row.id;
    button.append(element("code", "", row.id), element("span", "", row.status),
      element("strong", "", row.minutes ? `${row.minutes} dk` : `${row.low_points} kısa`));
    button.addEventListener("click", () => { selectedPriorityId = row.id; renderPriorityDetail(); });
    list.append(button);
  }
  select.addEventListener("change", () => { selectedPriorityId = select.value; renderPriorityDetail(); });
  selectedPriorityId = operationData.priority[0].id;
  renderPriorityDetail();
}

function createEventCard(event) {
  const card = element("article", "event-card");
  const heading = element("div", "event-heading");
  heading.append(element("span", `event-type ${event.type}`, event.type === "peer" ? "Filo kıyası" : "Büyük tahmin sapması"));
  heading.append(element("time", "", dateLabel(event.time)));
  card.append(heading);

  if (event.type === "peer") {
    card.append(element("h3", "", `${event.inverters.length} inverter · ${event.duration_minutes} dakika`));
    card.append(element("p", "", `Bu cihazlar filonun aynı andaki üretim düzeyinden ayrıldı: ${event.inverters.join(", ")}.`));
    card.append(element("small", "", `Bitiş: ${dateLabel(event.end)} · Bu bir neden/arıza teşhisi değildir.`));
  } else {
    const direction = event.difference < 0 ? "gerçek güç tahminden düşük" : "gerçek güç tahminden yüksek";
    card.append(element("h3", "", `${formatInteger.format(Math.abs(event.difference))} güç farkı`));
    card.append(element("p", "", `Tahmin ${formatInteger.format(event.forecast)}, gerçek ${formatInteger.format(event.actual)}; ${direction}.`));
    card.append(element("small", "", `En büyük bireysel hatalar: ${event.top_inverters.map((item) => item.id).join(", ")} · Önceden düşüş riski işaretlenen inverter: ${event.risk_alerts_before}`));
  }
  return card;
}

function renderEvents() {
  const filter = document.getElementById("event-filter").value;
  const events = operationData.events.filter((event) => filter === "all" || event.type === filter);
  const list = document.getElementById("event-list");
  list.replaceChildren();
  for (const event of events.slice(0, visibleEvents)) list.append(createEventCard(event));
  document.getElementById("show-more-events").hidden = events.length <= visibleEvents;
}

function initializeOperations() {
  if (!operationData?.metrics || !operationData?.events) {
    document.querySelector("main").textContent = "Operasyon verisi bulunamadı. Önce src/plant_model.py dosyasını çalıştır.";
    return;
  }
  const metrics = operationData.metrics;
  document.getElementById("risk-precision").textContent = formatPercent.format(metrics.test_precision);
  document.getElementById("risk-recall").textContent = formatPercent.format(metrics.test_recall);
  document.getElementById("peer-incidents").textContent = String(metrics.peer_incidents);
  document.getElementById("event-count").textContent = String(metrics.operator_events);
  document.getElementById("drop-limit").textContent = formatNumber.format(metrics.drop_limit);
  document.getElementById("risk-alerts").textContent = formatInteger.format(metrics.test_risk_alerts);
  document.getElementById("risk-correct").textContent = `${metrics.test_correct_risk_alerts} isabetli`;
  document.getElementById("risk-lift").textContent = `${formatNumber.format(metrics.precision_lift)}×`;
  document.getElementById("risk-reading").textContent = `Son testte ${formatInteger.format(metrics.test_day_examples)} gündüz kaydının ${metrics.test_drop_events} tanesinde sert düşüş oldu (${formatPercent.format(metrics.test_prevalence)}). Model ${metrics.test_risk_alerts} uyarının ${metrics.test_correct_risk_alerts} tanesinde haklı çıktı ve gerçek düşüşlerin ${formatPercent.format(metrics.test_recall)} bölümünü yakaladı.`;
  renderPeer();
  renderPriority();
  renderEvents();
  document.getElementById("event-filter").addEventListener("change", () => { visibleEvents = 6; renderEvents(); });
  document.getElementById("show-more-events").addEventListener("click", () => { visibleEvents += 6; renderEvents(); });
}

initializeOperations();
