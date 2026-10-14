"""Tahmin aralığı ve inverter inceleme sırasının temel kuralları."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from operations_model import build_priority  # noqa: E402
from uncertainty import interval_for_point  # noqa: E402


class UncertaintyPriorityTests(unittest.TestCase):
    def test_interval_is_nonnegative_ordered_and_contains_point(self):
        band = {"edges": [50, 150], "widths": [5, 20, 30, 40]}
        lower, upper = interval_for_point(band, [0, 100, 200], [3, 100, 200])
        np.testing.assert_array_equal(lower, [0, 70, 160])
        np.testing.assert_array_equal(upper, [8, 130, 240])

    def test_priority_uses_sustained_episode_before_short_low_points(self):
        times = pd.date_range("2020-06-14 11:00", periods=4, freq="15min")
        radar = pd.DataFrame([
            {"TARGET_TIME": time, "SOURCE_KEY": inverter, "eligible": True,
             "low_relative_power": inverter == "A" or index == 0,
             "peer_ratio": 0.4 if inverter == "A" else (0.65 if index == 0 else 1.0)}
            for inverter in ("A", "B") for index, time in enumerate(times)
        ])
        summary = pd.DataFrame([
            {"SOURCE_KEY": "B", "episodes": 0, "low_points": 1,
             "eligible_points": 4, "worst_ratio": 0.65},
            {"SOURCE_KEY": "A", "episodes": 1, "low_points": 4,
             "eligible_points": 4, "worst_ratio": 0.4},
        ])
        episodes = pd.DataFrame([{
            "inverter": "A", "start": times[0], "end": times[-1],
            "duration_minutes": 60,
        }])
        test = pd.DataFrame([
            {"SOURCE_KEY": inverter, "NEXT_AC_POWER": 10.0, "MODEL_PREDICTION": 12.0}
            for inverter in ("A", "B")
        ])
        with tempfile.TemporaryDirectory() as directory:
            priority, series = build_priority(radar, summary, episodes, test, Path(directory))
        self.assertEqual(priority.iloc[0]["SOURCE_KEY"], "A")
        self.assertEqual(priority.iloc[0]["episode_minutes"], 60)
        self.assertEqual(priority.iloc[1]["priority"], "İzle")
        self.assertEqual(len(series["A"]["points"]), 4)


if __name__ == "__main__":
    unittest.main()
