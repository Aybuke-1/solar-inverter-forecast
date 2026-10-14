"""Yerel HTTP ölçüm akışı: geçmiş kayıtları cihaz paketi gibi sırayla işle."""

import argparse
import json
import math
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import joblib
import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
DASHBOARD_DIR = PROJECT_DIR / "dashboard"
FORECAST_INPUTS = [
    "AC_POWER", "IRRADIATION", "AMBIENT_TEMPERATURE",
    "MODULE_TEMPERATURE", "HOUR", "MINUTE",
]
RISK_INPUTS = FORECAST_INPUTS + ["POWER_CHANGE_15", "IRRADIATION_CHANGE_15"]


def load_replay_packets() -> list[dict]:
    """Son test gününün yalnızca o ana ait ham ölçümlerini paketle."""
    generation = pd.read_csv(RAW_DIR / "Plant_1_Generation_Data.csv")
    weather = pd.read_csv(RAW_DIR / "Plant_1_Weather_Sensor_Data.csv")
    generation["DATE_TIME"] = pd.to_datetime(generation["DATE_TIME"], format="%d-%m-%Y %H:%M")
    weather["DATE_TIME"] = pd.to_datetime(weather["DATE_TIME"], format="%Y-%m-%d %H:%M:%S")
    day = generation["DATE_TIME"].max().date()
    generation = generation[(generation["DATE_TIME"].dt.date == day) & (generation["DATE_TIME"].dt.hour >= 7)]
    weather = weather[(weather["DATE_TIME"].dt.date == day) & (weather["DATE_TIME"].dt.hour >= 7)]
    merged = generation[["DATE_TIME", "SOURCE_KEY", "AC_POWER"]].merge(
        weather[["DATE_TIME", "IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE"]],
        on="DATE_TIME", validate="many_to_one",
    )
    packets = []
    for moment, rows in merged.groupby("DATE_TIME", sort=True):
        first = rows.iloc[0]
        packets.append({
            "timestamp": moment.isoformat(),
            "source": "historical-replay",
            "weather": {
                "irradiation": float(first["IRRADIATION"]),
                "ambient_temperature": float(first["AMBIENT_TEMPERATURE"]),
                "module_temperature": float(first["MODULE_TEMPERATURE"]),
            },
            "inverters": [
                {"id": str(row.SOURCE_KEY), "ac_power": float(row.AC_POWER)}
                for row in rows.sort_values("SOURCE_KEY").itertuples(index=False)
            ],
        })
    if not packets:
        raise ValueError("Son güne ait oynatılacak ölçüm bulunamadı.")
    return packets


def finite_number(value, name: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} sonlu bir sayı olmalı.")
    if nonnegative and value < 0:
        raise ValueError(f"{name} negatif olamaz.")
    return float(value)


class LiveEngine:
    """Her paketi geldiği anda tahmin eder; hedef ölçüm gelince sonucu açar."""

    def __init__(self, forecast_bundle: dict, risk_bundle: dict):
        self.forecast = forecast_bundle
        self.risk = risk_bundle
        self.allowed_ids = set(forecast_bundle["source_keys"])
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.last_time = None
            self.last_readings = {}
            self.pending = None
            self.packet_count = 0
            self.current = None
            self.revealed = None
            self.history = []
            self.events = []

    def receive(self, packet: dict) -> dict:
        # Tüm doğrulamayı durum değişmeden önce yap.
        if not isinstance(packet, dict):
            raise ValueError("Paket JSON nesnesi olmalı.")
        try:
            moment = datetime.fromisoformat(packet["timestamp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Geçerli bir timestamp gerekli.") from exc
        if moment.tzinfo is not None:
            raise ValueError("Bu örnekte saat dilimsiz yerel zaman kullanılmalı.")
        if moment.minute % 15 or moment.second or moment.microsecond:
            raise ValueError("Ölçüm saati 15 dakikalık tam aralıkta olmalı.")
        if packet.get("source") not in ("historical-replay", "device-gateway"):
            raise ValueError("source historical-replay veya device-gateway olmalı.")
        weather = packet.get("weather")
        if not isinstance(weather, dict):
            raise ValueError("weather nesnesi gerekli.")
        irradiation = finite_number(weather.get("irradiation"), "irradiation", nonnegative=True)
        ambient = finite_number(weather.get("ambient_temperature"), "ambient_temperature")
        module = finite_number(weather.get("module_temperature"), "module_temperature")
        readings = packet.get("inverters")
        if not isinstance(readings, list) or not readings:
            raise ValueError("En az bir inverter ölçümü gerekli.")
        powers = {}
        for reading in readings:
            if not isinstance(reading, dict):
                raise ValueError("Her inverter ölçümü nesne olmalı.")
            inverter = reading.get("id")
            if inverter not in self.allowed_ids or inverter in powers:
                raise ValueError("Bilinmeyen veya yinelenen inverter kimliği.")
            powers[inverter] = finite_number(reading.get("ac_power"), "ac_power", nonnegative=True)
        if set(powers) != self.allowed_ids:
            raise ValueError("Toplam güç için tüm inverterlerin ölçümü gerekli.")

        with self.lock:
            if self.last_time is not None and moment <= self.last_time:
                raise ValueError("Ölçüm zamanı önceki paketten sonra olmalı.")
            ids = sorted(powers)
            inputs = pd.DataFrame([{
                "AC_POWER": powers[inverter],
                "IRRADIATION": irradiation,
                "AMBIENT_TEMPERATURE": ambient,
                "MODULE_TEMPERATURE": module,
                "HOUR": moment.hour,
                "MINUTE": moment.minute,
                "SOURCE_KEY": inverter,
            } for inverter in ids])
            forecast_features = pd.get_dummies(
                inputs[FORECAST_INPUTS + ["SOURCE_KEY"]], columns=["SOURCE_KEY"], dtype=int
            ).reindex(columns=self.forecast["columns"], fill_value=0)
            predictions = np.maximum(self.forecast["model"].predict(forecast_features), 0)
            if not np.isfinite(predictions).all():
                raise ValueError("Model sonlu tahmin üretemedi.")
            predicted_by_id = dict(zip(ids, map(float, predictions)))

            # Risk modeli yalnızca tam 15 dakika önceki ölçüm varsa çalışır.
            risk_ids = [
                inverter for inverter in ids
                if irradiation > 0 and inverter in self.last_readings
                and moment - self.last_readings[inverter]["time"] == timedelta(minutes=15)
            ]
            risk_flags = []
            if risk_ids:
                risk_inputs = inputs[inputs["SOURCE_KEY"].isin(risk_ids)].copy()
                risk_inputs["POWER_CHANGE_15"] = [
                    powers[inverter] - self.last_readings[inverter]["power"]
                    for inverter in risk_inputs["SOURCE_KEY"]
                ]
                risk_inputs["IRRADIATION_CHANGE_15"] = [
                    irradiation - self.last_readings[inverter]["irradiation"]
                    for inverter in risk_inputs["SOURCE_KEY"]
                ]
                risk_features = pd.get_dummies(
                    risk_inputs[RISK_INPUTS + ["SOURCE_KEY"]], columns=["SOURCE_KEY"], dtype=int
                ).reindex(columns=self.risk["columns"], fill_value=0)
                scores = self.risk["model"].predict_proba(risk_features)[:, 1]
                risk_flags = [
                    inverter for inverter, score in zip(risk_inputs["SOURCE_KEY"], scores)
                    if score >= self.risk["risk_score_limit"]
                ]

            revealed = None
            if self.pending and self.pending["target_time"] == moment and set(self.pending["ids"]) == set(ids):
                actual = float(sum(powers.values()))
                forecast = self.pending["forecast"]
                error = abs(actual - forecast)
                alert = error > self.forecast["alert_threshold"]
                revealed = {
                    "time": moment.isoformat(), "actual": actual,
                    "forecast": forecast, "error": error, "alert": alert,
                }
                if alert:
                    self.events.append({
                        "time": moment.isoformat(), "error": error,
                        "message": "Toplam güç tahmini ile ölçüm arasında büyük sapma",
                    })
            self.revealed = revealed
            self.pending = {
                "target_time": moment + timedelta(minutes=15),
                "forecast": float(sum(predicted_by_id.values())), "ids": ids,
            }
            self.last_time = moment
            self.last_readings = {
                inverter: {"time": moment, "power": powers[inverter], "irradiation": irradiation}
                for inverter in ids
            }
            self.packet_count += 1
            self.current = {
                "time": moment.isoformat(), "power": float(sum(powers.values())),
                "forecast": self.pending["forecast"],
                "target_time": self.pending["target_time"].isoformat(),
                "inverter_count": len(ids), "irradiation": irradiation,
                "risk_count": len(risk_flags), "risk_ids": risk_flags,
                "risk_examined": len(risk_ids), "source": packet["source"],
            }
            self.history.append({
                "time": moment.isoformat(), "actual": self.current["power"],
                "forecast_for_next": self.current["forecast"],
                "revealed_forecast": revealed["forecast"] if revealed else None,
                "alert": revealed["alert"] if revealed else False,
            })
            return self.snapshot()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "packet_count": self.packet_count, "current": self.current,
                "revealed": self.revealed, "history": list(self.history),
                "events": list(self.events),
            }


class ReplayController:
    def __init__(self, packets: list[dict], port: int):
        self.packets = packets
        self.port = port
        self.lock = threading.RLock()
        self.index = 0
        self.playing = False
        self.interval = 1.0
        self.next_due = 0.0
        self.stopping = threading.Event()

    def snapshot(self):
        with self.lock:
            return {"playing": self.playing, "sent": self.index,
                    "total": len(self.packets), "interval_ms": round(self.interval * 1000)}

    def send_next(self, *, require_playing=False):
        with self.lock:
            if require_playing and not self.playing:
                return
            if self.index >= len(self.packets):
                self.playing = False
                return
            data = json.dumps(self.packets[self.index]).encode("utf-8")
            request = Request(
                f"http://127.0.0.1:{self.port}/api/telemetry", data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(request, timeout=10):
                pass
            self.index += 1
            self.next_due = time.monotonic() + self.interval
            if self.index >= len(self.packets):
                self.playing = False

    def run(self):
        while not self.stopping.wait(0.05):
            with self.lock:
                due = self.playing and time.monotonic() >= self.next_due
            if due:
                try:
                    self.send_next(require_playing=True)
                except (URLError, ValueError) as exc:
                    with self.lock:
                        self.playing = False
                    print("Ölçüm akışı durdu:", exc)


def make_handler(engine: LiveEngine, controller: ReplayController):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, payload: dict):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def read_json(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 100_000:
                raise ValueError("JSON paketi boş veya çok büyük.")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            if self.path == "/api/state":
                self.respond(200, {**engine.snapshot(), "replay": controller.snapshot()})
                return
            pages = {
                "live.html", "live.js", "style.css", "index.html", "app.js", "data.js",
                "analysis.html", "analysis.js", "simulation.html", "replay.js",
                "operations.html", "operations.js", "operations_data.js",
            }
            reports = {
                "reports/proje_ozeti.md", "reports/figures/ramp_precision_recall.png",
                "reports/figures/peer_case.png",
            }
            name = "live.html" if self.path == "/" else self.path.removeprefix("/")
            if name not in pages and name not in reports:
                self.send_error(404)
                return
            path = (DASHBOARD_DIR / name) if name in pages else (PROJECT_DIR / name)
            data = path.read_bytes()
            kind = (
                "text/javascript" if name.endswith(".js") else
                "text/css" if name.endswith(".css") else
                "image/png" if name.endswith(".png") else
                "text/markdown" if name.endswith(".md") else "text/html"
            )
            self.send_response(200)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                body = self.read_json()
                if self.path == "/api/telemetry":
                    self.respond(200, engine.receive(body))
                elif self.path == "/api/control":
                    if not isinstance(body, dict):
                        raise ValueError("Kontrol JSON nesnesi olmalı.")
                    action = body.get("action")
                    if action == "start":
                        with controller.lock:
                            controller.playing = controller.index < len(controller.packets)
                            controller.next_due = time.monotonic()
                    elif action == "pause":
                        with controller.lock:
                            controller.playing = False
                    elif action == "step":
                        with controller.lock:
                            controller.playing = False
                        controller.send_next()
                    elif action == "reset":
                        with controller.lock:
                            controller.playing = False
                            engine.reset()
                            controller.index = 0
                    elif action == "speed":
                        interval = finite_number(body.get("interval_ms"), "interval_ms", nonnegative=True)
                        if interval < 100 or interval > 10_000:
                            raise ValueError("Hız 100–10000 ms aralığında olmalı.")
                        with controller.lock:
                            controller.interval = interval / 1000
                    else:
                        raise ValueError("Bilinmeyen kontrol komutu.")
                    self.respond(200, {**engine.snapshot(), "replay": controller.snapshot()})
                else:
                    self.send_error(404)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                self.respond(400, {"error": str(exc)})

        def log_message(self, *_args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Yerel inverter ölçüm akışı demosu")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    forecast_path = PROJECT_DIR / "models" / "forecast_bundle.joblib"
    risk_path = PROJECT_DIR / "models" / "risk_bundle.joblib"
    if not forecast_path.exists() or not risk_path.exists():
        raise SystemExit("Önce .\\.venv\\Scripts\\python.exe src\\plant_model.py çalıştırıp modelleri kaydet.")
    engine = LiveEngine(joblib.load(forecast_path), joblib.load(risk_path))
    packets = load_replay_packets()
    controller = ReplayController(packets, args.port)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine, controller))
    worker = threading.Thread(target=controller.run, daemon=True)
    worker.start()
    print(f"Yerel demo: http://127.0.0.1:{args.port}/")
    print(f"{len(packets)} tarihsel ölçüm paketi hazır. Durdurmak için Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stopping.set()
        server.server_close()


if __name__ == "__main__":
    main()
