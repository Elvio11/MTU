import unittest
import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from src.python.shared.telegram_auth import generate_otp, verify_otp


class TestTelegramAuth(unittest.TestCase):
    def setUp(self):
        self.seed = "pre_shared_secret_seed_123"

    def test_01_generate_otp(self):
        """Test OTP generation per Section 4.3"""
        otp = generate_otp(self.seed)
        self.assertEqual(len(otp), 8, "OTP must be 8 characters")

    def test_02_verify_valid_otp(self):
        """Test valid OTP verification"""
        otp = generate_otp(self.seed)
        self.assertTrue(verify_otp(self.seed, otp))

    def test_03_verify_invalid_otp(self):
        """Test invalid OTP rejection"""
        self.assertFalse(verify_otp(self.seed, "invalid123"))

    def test_04_verify_with_time_window(self):
        """Test OTP works within time window"""
        current_ts = int(time.time())
        otp = generate_otp(self.seed, current_ts)
        # Verify with current window (should pass)
        self.assertTrue(verify_otp(self.seed, otp, window=1))
        # Verify with wrong OTP (should fail)
        self.assertFalse(verify_otp(self.seed, "wrong123", window=1))


if __name__ == "__main__":
    unittest.main()
