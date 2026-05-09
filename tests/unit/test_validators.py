import unittest
import sys
import os

# Add D:/Trader/src to path so 'python.shared.validators' works
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, src_path)

from python.shared.validators import (
    is_valid_base58_pubkey,
    truncate_string,
    is_valid_metadata_uri,
    is_valid_social_url,
    is_valid_positive_number,
)


class TestValidators(unittest.TestCase):
    def test_01_valid_base58_pubkey(self):
        """Test valid Solana pubkey (32 bytes base58)"""
        import base58

        valid_key = base58.b58encode(os.urandom(32)).decode()
        self.assertTrue(is_valid_base58_pubkey(valid_key))
        self.assertFalse(is_valid_base58_pubkey("invalid"))

    def test_02_truncate_string(self):
        self.assertEqual(truncate_string("hello", 3), "hel")
        self.assertEqual(truncate_string("hi", 3), "hi")

    def test_03_valid_metadata_uri(self):
        self.assertTrue(is_valid_metadata_uri("https://example.com/meta"))
        self.assertFalse(is_valid_metadata_uri("http://example.com"))  # No HTTPS
        self.assertFalse(is_valid_metadata_uri("data:text/html,<h1>test</h1>"))
        self.assertFalse(is_valid_metadata_uri("javascript:alert(1)"))

    def test_04_valid_social_url(self):
        self.assertTrue(is_valid_social_url("https://twitter.com/user"))
        self.assertTrue(is_valid_social_url("https://t.me/channel"))
        self.assertFalse(is_valid_social_url("https://evil.com/phishing"))

    def test_05_valid_positive_number(self):
        self.assertTrue(is_valid_positive_number(10.5))
        self.assertFalse(is_valid_positive_number(-1))
        self.assertFalse(is_valid_positive_number(0))
        self.assertFalse(is_valid_positive_number("not a number"))


if __name__ == "__main__":
    unittest.main()
