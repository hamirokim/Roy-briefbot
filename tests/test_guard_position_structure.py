import unittest
from unittest.mock import patch

import pandas as pd

from src.agents.guard import _assess_position_structure, _confirmed_pivots


def _frame(closes):
    return pd.DataFrame(
        {
            "High": [value + 1.0 for value in closes],
            "Low": [value - 1.0 for value in closes],
            "Close": closes,
        }
    )


class PositionStructureTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "pivot_span": 2,
            "pivot_scan_bars": 90,
            "breakout_lookback_bars": 20,
            "extension_up_streak": 3,
            "extension_atr_multiple": 1.5,
        }

    def test_confirmed_pivots_require_unique_extreme(self):
        values = [1, 2, 5, 2, 1, 1, 4, 1, 1]
        self.assertEqual(_confirmed_pivots(values, 2, high=True), [(2, 5), (6, 4)])

    def test_recent_small_high_breakout_is_reported_as_hold(self):
        closes = (
            [90 + ((idx % 5) * 0.3) for idx in range(30)]
            + [94, 96, 99, 103, 100, 98, 99, 100, 102, 104]
            + [102, 101, 102, 103, 104, 105, 106]
        )
        result = _assess_position_structure(_frame(closes), self.cfg, sl_price=97)

        self.assertEqual(result["status"], "BREAKOUT_HOLD")
        self.assertEqual(result["label"], "소고점 돌파 구조 유지")
        self.assertIsNotNone(result["breakout_level"])
        if result.get("resistance") is not None:
            self.assertGreater(result["resistance"], result["close"])
            self.assertGreater(result["resistance"], result["breakout_level"])
        self.assertGreaterEqual(result["up_streak"], 3)
        self.assertTrue(result["pause_watch"])

    def test_no_breakout_does_not_claim_hold(self):
        closes = [100 + ((idx % 6) - 3) * 0.5 for idx in range(45)]
        result = _assess_position_structure(_frame(closes), self.cfg)

        self.assertEqual(result["status"], "NO_RECENT_BREAKOUT")

    def test_breakout_level_loss_can_be_support_watch_before_structure_break(self):
        closes = (
            [90 + ((idx % 5) * 0.3) for idx in range(30)]
            + [94, 96, 99, 103, 100, 98, 99, 100, 102, 104]
            + [102, 101, 102, 105, 107, 103, 102.5]
        )
        result = _assess_position_structure(_frame(closes), self.cfg, sl_price=97)

        self.assertEqual(result["status"], "SUPPORT_WATCH")
        self.assertLess(result["close"], result["breakout_level"])
        self.assertGreater(result["close"], result["support"])

    @patch("src.agents.guard._confirmed_pivots")
    def test_resistance_must_be_above_both_close_and_breakout(self, pivots_mock):
        pivots_mock.side_effect = lambda values, span, high: (
            [(5, 120.0), (10, 109.5), (30, 110.0)]
            if high else [(35, 105.0), (43, 106.0)]
        )
        closes = [100.0] * 40 + [109.0, 111.0, 112.0, 108.0, 107.0, 109.0]
        result = _assess_position_structure(_frame(closes), self.cfg)
        self.assertEqual(result["breakout_level"], 110.0)
        self.assertEqual(result["resistance"], 120.0)

    def test_short_history_fails_closed(self):
        result = _assess_position_structure(_frame([100.0] * 20), self.cfg)
        self.assertEqual(result["status"], "DATA_SHORT")


if __name__ == "__main__":
    unittest.main()
