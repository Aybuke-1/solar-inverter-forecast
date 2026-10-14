"use strict";

const data = window.dashboardData;
const number = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 });
const svgNS = "http://www.w3.org/2000/svg";
const colors = { actual: "#77adff", model: "#ffb15b", baseline: "#50d5b0" };
let selectedId = "bvBOhCH3iADSZry";

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(svgNS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  return element;
}

function addSvgText(parent, text, attributes) {
  const element = svgElement("text", attributes);
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

function renderChart() {
  const svg = document.querySelector("#power-chart");
  const series = data.plant_series;
  const visible = {
    actual: true,
    model: document.querySelector('[data-series="model"]').checked,
    baseline: document.querySelector('[data-series="baseline"]').checked,
  };
  const width = 960;
  const height = 360;
  const margin = { left: 72, right: 18, top: 16, bottom: 43 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const keys = Object.keys(visible).filter((key) => visible[key]);
  const maximum = Math.max(...series.flatMap((row) => keys.map((key) => row[key]))) * 1.08 || 1;
  const x = (index) => margin.left + (index / (series.length - 1)) * plotWidth;
  const y = (value) => margin.top + plotHeight - (value / maximum) * plotHeight;
  svg.replaceChildren();

  for (let tick = 0; tick <= 4; tick += 1) {
    const value = (maximum / 4) * tick;
    const position = y(value);
    svg.appendChild(svgElement("line", { x1: margin.left, x2: width - margin.right, y1: position, y2: position, stroke: "#31485f", "stroke-width": 1 }));
    addSvgText(svg, integer.format(value), { x: margin.left - 10, y: position + 4, "text-anchor": "end", fill: "#9bb0c5", "font-size": 12 });
  }

  for (let tick = 0; tick <= 4; tick += 1) {
    const index = Math.round(((series.length - 1) / 4) * tick);
    const position = x(index);
    svg.appendChild(svgElement("line", { x1: position, x2: position, y1: margin.top, y2: margin.top + plotHeight, stroke: "#26394e", "stroke-width": 1 }));
    addSvgText(svg, series[index].time, { x: position, y: height - 10, "text-anchor": "middle", fill: "#9bb0c5", "font-size": 12 });
  }

  for (const key of ["baseline", "model", "actual"]) {
    if (!visible[key]) continue;
    const points = series.map((row, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(row[key]).toFixed(2)}`).join(" ");
    svg.appendChild(svgElement("path", { d: points, fill: "none", stroke: colors[key], "stroke-width": key === "actual" ? 3 : 2.4, "stroke-linecap": "round", "stroke-linejoin": "round" }));
  }

  svg.appendChild(svgElement("line", { id: "focus-line", x1: 0, x2: 0, y1: margin.top, y2: margin.top + plotHeight, stroke: "#c8d8e6", "stroke-width": 1, "stroke-dasharray": "4 4", visibility: "hidden" }));
  svg.dataset.marginLeft = String(margin.left);
  svg.dataset.plotWidth = String(plotWidth);
}

function showChartTooltip(event) {
  const svg = document.querySelector("#power-chart");
  const tooltip = document.querySelector("#chart-tooltip");
  const wrapper = document.querySelector(".chart-wrap");
  const rect = svg.getBoundingClientRect();
  const svgX = ((event.clientX - rect.left) / rect.width) * 960;
  const index = Math.max(0, Math.min(data.plant_series.length - 1, Math.round(((svgX - Number(svg.dataset.marginLeft)) / Number(svg.dataset.plotWidth)) * (data.plant_series.length - 1))));
  const point = data.plant_series[index];
  const focusX = Number(svg.dataset.marginLeft) + (index / (data.plant_series.length - 1)) * Number(svg.dataset.plotWidth);
  const focus = document.querySelector("#focus-line");
  focus.setAttribute("x1", focusX);
  focus.setAttribute("x2", focusX);
  focus.setAttribute("visibility", "visible");

  tooltip.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `${data.plant_day} · ${point.time}`;
  tooltip.appendChild(heading);
  for (const [label, value] of [["Gerçek", point.actual], ["Model", point.model], ["Basit tahmin", point.baseline]]) {
    const line = document.createElement("div");
    line.textContent = `${label}: ${integer.format(value)}`;
    tooltip.appendChild(line);
  }
  tooltip.hidden = false;
  const wrapRect = wrapper.getBoundingClientRect();
  const left = Math.max(8, Math.min(event.clientX - wrapRect.left + 14, wrapper.clientWidth - tooltip.offsetWidth - 8));
  const preferredTop = event.clientY - wrapRect.top - tooltip.offsetHeight - 12;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${preferredTop > 8 ? preferredTop : event.clientY - wrapRect.top + 13}px`;
}

function renderSelected() {
  const selected = data.inverters.find((row) => row.id === selectedId);
  document.querySelector("#inverter-select").value = selectedId;
  document.querySelector("#selected-id").textContent = selected.id;
  document.querySelector("#selected-baseline").textContent = number.format(selected.baseline_mae);
  document.querySelector("#selected-model").textContent = number.format(selected.model_mae);
  document.querySelector("#selected-delta").textContent = `${selected.improvement > 0 ? "+" : ""}${number.format(selected.improvement)}`;
  const status = document.querySelector("#selected-status");
  const improved = selected.improvement > 0;
  status.textContent = improved ? "Model daha iyi" : "Basit tahmin daha iyi";
  status.classList.toggle("negative", !improved);
  document.querySelectorAll(".bar-row").forEach((row) => row.classList.toggle("active", row.dataset.id === selectedId));
}

function renderInverters() {
  const select = document.querySelector("#inverter-select");
  const bars = document.querySelector("#inverter-bars");
  const sorted = [...data.inverters].sort((a, b) => b.improvement - a.improvement);
  const maxAbs = Math.max(...sorted.map((row) => Math.abs(row.improvement)));
  for (const row of sorted) {
    const option = document.createElement("option");
    option.value = row.id;
    option.textContent = row.id;
    select.appendChild(option);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "bar-row";
    button.dataset.id = row.id;
    button.title = `${row.id}: basit tahmin ${number.format(row.baseline_mae)}, model ${number.format(row.model_mae)}`;
    const id = document.createElement("span");
    id.className = "bar-id";
    id.textContent = row.id;
    const track = document.createElement("span");
    track.className = "bar-track";
    const zero = document.createElement("span");
    zero.className = "bar-zero";
    const fill = document.createElement("span");
    fill.className = `bar-fill${row.improvement < 0 ? " negative" : ""}`;
    fill.style.width = `${(Math.abs(row.improvement) / maxAbs) * 47}%`;
    fill.style.left = row.improvement < 0 ? `${50 - (Math.abs(row.improvement) / maxAbs) * 47}%` : "50%";
    track.append(zero, fill);
    const value = document.createElement("span");
    value.className = "bar-value";
    value.textContent = `${row.improvement > 0 ? "+" : ""}${number.format(row.improvement)}`;
    button.append(id, track, value);
    button.addEventListener("click", () => {
      selectedId = row.id;
      renderSelected();
    });
    bars.appendChild(button);
  }
  if (!data.inverters.some((row) => row.id === selectedId)) selectedId = sorted[0].id;
  select.addEventListener("change", () => {
    selectedId = select.value;
    renderSelected();
  });
  renderSelected();
}

function initialize() {
  if (!data || !data.metrics || !data.plant_series || !data.inverters) {
    document.querySelector("main").textContent = "Sonuç verisi bulunamadı. Önce src/plant_model.py dosyasını çalıştır.";
    return;
  }
  const metrics = data.metrics;
  document.querySelector("#metric-inverters").textContent = integer.format(metrics.inverters);
  document.querySelector("#metric-examples").textContent = integer.format(metrics.examples);
  document.querySelector("#metric-mae").textContent = number.format(metrics.test_model_mae);
  document.querySelector("#metric-improved").textContent = `${metrics.inverters_improved}/${metrics.inverters}`;
  document.querySelector("#chart-subtitle").textContent = `${data.plant_day} · 15 dakika sonrası · ${metrics.plant_time_points} test zaman noktası`;
  renderChart();
  renderInverters();
  document.querySelectorAll("[data-series]").forEach((input) => input.addEventListener("change", renderChart));
  document.querySelector("#power-chart").addEventListener("mousemove", showChartTooltip);
  document.querySelector("#power-chart").addEventListener("mouseleave", () => {
    document.querySelector("#chart-tooltip").hidden = true;
    document.querySelector("#focus-line").setAttribute("visibility", "hidden");
  });
}

initialize();
