"""Ölçüm akışında geleceği önceden göstermeme ve paket doğrulama testleri."""

import sys
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from live_demo import LiveEngine, ReplayController, load_replay_packets, make_handler  # noqa: E402


class ForecastStub:
    def predict(self, rows):
        return rows["AC_POWER"].to_numpy() + 10


class RiskStub:
    def predict_proba(self, rows):
        score = np.where(rows["POWER_CHANGE_15"].to_numpy() < -10, 0.8, 0.1)
        return np.column_stack([1 - score, score])


def packet(moment, first, second):
    return {
        "timestamp": moment, "source": "historical-replay",
        "weather": {"irradiation": 0.6, "ambient_temperature": 25, "module_temperature": 31},
        "inverters": [{"id": "A", "ac_power": first}, {"id": "B", "ac_power": second}],
    }


class LiveDemoTests(unittest.TestCase):
    def setUp(self):
        columns = [
            "AC_POWER", "IRRADIATION", "AMBIENT_TEMPERATURE", "MODULE_TEMPERATURE",
            "HOUR", "MINUTE", "SOURCE_KEY_A", "SOURCE_KEY_B",
        ]
        self.engine = LiveEngine(
            {"model": ForecastStub(), "columns": columns, "source_keys": ["A", "B"], "alert_threshold": 30},
            {"model": RiskStub(), "columns": columns + ["POWER_CHANGE_15", "IRRADIATION_CHANGE_15"],
             "risk_score_limit": 0.5},
        )

    def test_reveals_actual_only_when_next_packet_arrives(self):
        first = self.engine.receive(packet("2020-06-17T10:00:00", 100, 100))
        self.assertIsNone(first["revealed"])
        self.assertEqual(first["current"]["forecast"], 220)
        self.assertEqual(first["current"]["risk_examined"], 0)
        self.assertEqual(first["events"], [])

        second = self.engine.receive(packet("2020-06-17T10:15:00", 50, 100))
        self.assertEqual(second["revealed"]["actual"], 150)
        self.assertEqual(second["revealed"]["forecast"], 220)
        self.assertEqual(second["revealed"]["error"], 70)
        self.assertEqual(second["current"]["risk_ids"], ["A"])
        self.assertEqual(len(second["events"]), 1)

    def test_gap_does_not_compare_old_forecast_or_use_stale_risk_input(self):
        self.engine.receive(packet("2020-06-17T10:00:00", 100, 100))
        state = self.engine.receive(packet("2020-06-17T10:45:00", 50, 100))
        self.assertIsNone(state["revealed"])
        self.assertEqual(state["current"]["risk_examined"], 0)

    def test_invalid_packet_does_not_change_state(self):
        self.engine.receive(packet("2020-06-17T10:00:00", 100, 100))
        duplicate = packet("2020-06-17T10:15:00", 50, 100)
        duplicate["inverters"][1]["id"] = "A"
        with self.assertRaises(ValueError):
            self.engine.receive(duplicate)
        with self.assertRaises(ValueError):
            self.engine.receive(packet("2020-06-17T09:45:00", 50, 100))
        self.assertEqual(self.engine.snapshot()["packet_count"], 1)

    def test_replay_packets_contain_current_measurements_only(self):
        packets = load_replay_packets()
        self.assertGreater(len(packets), 50)
        self.assertEqual(len(packets[0]["inverters"]), 22)
        self.assertEqual(set(packets[0]), {"timestamp", "source", "weather", "inverters"})
        self.assertEqual(set(packets[0]["inverters"][0]), {"id", "ac_power"})

    def test_http_replay_reaches_model_and_reveals_next_result(self):
        packets = [
            packet("2020-06-17T10:00:00", 100, 100),
            packet("2020-06-17T10:15:00", 50, 100),
        ]
        controller = ReplayController(packets, 0)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.engine, controller))
        controller.port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            controller.send_next()
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/state", timeout=3) as response:
                first = json.load(response)
            self.assertEqual(first["packet_count"], 1)
            self.assertIsNone(first["revealed"])
            controller.send_next()
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/state", timeout=3) as response:
                second = json.load(response)
            self.assertEqual(second["revealed"]["actual"], 150)
            self.assertEqual(second["revealed"]["forecast"], 220)
            bad = Request(
                f"http://127.0.0.1:{server.server_port}/api/telemetry",
                data=json.dumps(packet("2020-06-17T10:00:00", 1, 1)).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                urlopen(bad, timeout=3)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
