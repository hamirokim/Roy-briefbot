import unittest

from src.agents.guard import _is_direct_company_news


class GuardNewsRelevanceTests(unittest.TestCase):
    def test_company_alias_in_headline_passes(self):
        self.assertTrue(
            _is_direct_company_news(
                {"headline": "ServiceNow raises full-year subscription outlook"},
                "NOW",
                ["ServiceNow"],
            )
        )

    def test_ambiguous_now_token_does_not_pass(self):
        self.assertFalse(
            _is_direct_company_news(
                {"headline": "Three software stocks to buy now"},
                "NOW",
                ["ServiceNow"],
            )
        )

    def test_competitor_roundup_does_not_pass(self):
        self.assertFalse(
            _is_direct_company_news(
                {"headline": "Adidas gains while footwear demand weakens"},
                "NKE",
                ["Nike"],
            )
        )

    def test_ticker_token_or_alias_passes(self):
        self.assertTrue(_is_direct_company_news({"headline": "NKE updates guidance"}, "NKE", ["Nike"]))
        self.assertTrue(_is_direct_company_news({"headline": "Clorox names new CFO"}, "CLX", ["Clorox"]))


if __name__ == "__main__":
    unittest.main()
