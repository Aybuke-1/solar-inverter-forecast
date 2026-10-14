"use strict";

const operationData = window.operationsData;
const formatNumber = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const formatInteger = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const formatPercent = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 });
let visibleEvents = 6;

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
  renderEvents();
  document.getElementById("event-filter").addEventListener("change", () => { visibleEvents = 6; renderEvents(); });
  document.getElementById("show-more-events").addEventListener("click", () => { visibleEvents += 6; renderEvents(); });
}

initializeOperations();
