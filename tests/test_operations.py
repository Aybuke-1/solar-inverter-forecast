"""Operasyon analizindeki zaman sırası ve uzun olay koşullarını kontrol et."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from operations_model import add_recent_changes, calculate_peer_radar  # noqa: E402


class OperationsTests(unittest.TestCase):
    def test_recent_change_does_not_bridge_missing_measurement(self):
        data = pd.DataFrame(
            {
                "SOURCE_KEY": ["A", "A", "A"],
                "DATE_TIME": pd.to_datetime(
                    ["2020-06-01 10:00", "2020-06-01 10:15", "2020-06-01 11:00"]
                ),
                "AC_POWER": [100.0, 80.0, 50.0],
                "IRRADIATION": [0.8, 0.7, 0.5],
                "NEXT_AC_POWER": [80.0, 50.0, 40.0],
            }
        )
        changes = add_recent_changes(data)
        self.assertTrue(pd.isna(changes.loc[0, "POWER_CHANGE_15"]))
        self.assertEqual(changes.loc[1, "POWER_CHANGE_15"], -20.0)
        self.assertTrue(pd.isna(changes.loc[2, "POWER_CHANGE_15"]))
        self.assertTrue(pd.isna(changes.loc[2, "IRRADIATION_CHANGE_15"]))

    def test_peer_event_requires_four_consecutive_intervals(self):
        devices = [f"INV-{number:02d}" for number in range(22)]
        training = pd.DataFrame(
            {
                "SOURCE_KEY": devices,
                "AC_POWER": [100.0] * len(devices),
                "IRRADIATION": [0.8] * len(devices),
            }
        )

        def evaluate(times):
            rows = []
            for time in pd.to_datetime(times):
                for device in devices:
                    rows.append(
                        {
                            "TARGET_TIME": time,
                            "SOURCE_KEY": device,
                            "NEXT_AC_POWER": 20.0 if device == devices[0] else 100.0,
                        }
                    )
            return calculate_peer_radar(training, pd.DataFrame(rows))[2]

        interrupted = evaluate(
            ["2020-06-01 11:00", "2020-06-01 11:15", "2020-06-01 11:30", "2020-06-01 12:00"]
        )
        self.assertTrue(interrupted.empty)

        complete = evaluate(
            ["2020-06-01 11:00", "2020-06-01 11:15", "2020-06-01 11:30", "2020-06-01 11:45"]
        )
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete.iloc[0]["inverter"], devices[0])
        self.assertEqual(complete.iloc[0]["duration_minutes"], 60)


if __name__ == "__main__":
    unittest.main()
