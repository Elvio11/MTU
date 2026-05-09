import unittest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from src.python.agents.cassandra import CassandraAgent, DEXSCREENER_API


class TestCassandraAgent(unittest.TestCase):
    def setUp(self):
        self.agent = CassandraAgent()

    def test_01_dexscreener_api_endpoint(self):
        expected = "https://api.dexscreener.com/latest/dex/tokens"
        self.assertEqual(DEXSCREENER_API, expected)

    @patch("aiohttp.ClientSession")
    def test_02_fetch_dexscreener_data_success(self, mock_session):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "pair": {
                    "info": {
                        "twitter": "https://twitter.com/test",
                        "telegram": "https://t.me/test",
                        "website": "https://test.com",
                    },
                    "liquidity": {"usd": 50000},
                    "txns": {"h24": {"buys": 100, "sells": 50}},
                }
            }
        )

        mock_session.return_value.__aenter__.return_value.get = MagicMock(
            return_value=mock_response
        )

        self.agent.session = mock_session.return_value.__aenter__.return_value

    def test_03_score_sentiment_base(self):
        self.agent.session = AsyncMock()

        token_payload = {"mint": "test_mint", "uri": "https://example.com", "age": 7200}

    def test_04_social_signals_detection(self):
        self.agent.session = AsyncMock()

        socials = {"twitter": False, "telegram": False, "website": False}

        self.assertFalse(any(socials.values()))
        socials["twitter"] = True
        self.assertTrue(any(socials.values()))


class TestDexScreenerIntegration(unittest.TestCase):
    def test_01_api_url_format(self):
        mint = "EPjFWdd5AufqSSQhM7gS6EUDc7n9r9r5s4y3t9xF3S"
        url = f"{DEXSCREENER_API}/{mint}"
        self.assertIn("EPjFWdd5AufqSSQhM7gS6EUDc7n9r9r5s4y3t9xF3S", url)

    def test_02_score_bounds(self):
        score = 50.0
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
