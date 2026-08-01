import unittest
from unittest.mock import Mock, patch

from src.collectors import macro_calendar


class FredFallbackTests(unittest.TestCase):
    @patch.object(macro_calendar, "FRED_API_KEY", "")
    @patch("src.collectors.macro_calendar.requests.get")
    def test_keyless_csv_returns_latest_first(self, get_mock):
        response = Mock(status_code=200)
        response.text = "observation_date,DFII10\n2026-07-29,1.80\n2026-07-30,.\n2026-07-31,1.90\n"
        get_mock.return_value = response
        rows = macro_calendar.fetch_fred_series("DFII10", lookback_days=30)
        self.assertEqual(rows, [
            {"date": "2026-07-31", "value": "1.90"},
            {"date": "2026-07-29", "value": "1.80"},
        ])
        self.assertIn("fredgraph.csv", get_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
