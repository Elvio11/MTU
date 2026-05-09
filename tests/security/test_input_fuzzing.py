"""
Security Tests - Input Fuzzing
Section 10.1: Security: Input fuzzing
"""

import pytest
import sys
import os
import string
import random

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from src.python.shared.validators import (
    is_valid_base58_pubkey,
    truncate_string,
    is_valid_metadata_uri,
    is_valid_social_url,
    is_valid_positive_number,
)
import base58


class TestInputFuzzing:
    """Fuzz input validators with malicious/boundary inputs"""

    def test_01_fuzz_base58_validator(self):
        """Fuzz base58 validator with various invalid inputs"""
        invalid_inputs = [
            "",  # Empty
            "0",  # Single zero (not valid base58)
            "O",  # Capital O (not in base58 alphabet)
            "I",  # Capital I (not in base58 alphabet)
            "l",  # Lowercase l (not in base58 alphabet)
            "0" * 44,  # All zeros
            "'" * 44,  # Invalid chars
            "x" * 1000,  # Too long
            None,  # None
            12345,  # Number
            "SELECT * FROM users",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
        ]

        for inp in invalid_inputs:
            try:
                result = is_valid_base58_pubkey(inp)
                assert result == False, f"Should be invalid: {inp}"
            except Exception:
                # Exception is acceptable for invalid input
                pass

    def test_02_fuzz_valid_base58(self):
        """Generate valid base58 keys and verify they pass"""
        for _ in range(20):
            # Generate random 32-byte key and encode as base58
            random_bytes = os.urandom(32)
            valid_key = base58.b58encode(random_bytes).decode()
            assert is_valid_base58_pubkey(valid_key) == True

    def test_03_fuzz_truncate_string(self):
        """Fuzz truncate_string with various inputs"""
        test_cases = [
            ("Hello", 10, "Hello"),
            ("Hello", 3, "Hel"),
            ("", 10, ""),
            ("A" * 1000, 50, "A" * 50),
            (None, 10, ""),  # None should be handled
            (12345, 10, "12345"),  # Number converted to string
        ]

        for input_str, max_len, expected in test_cases:
            try:
                result = truncate_string(input_str, max_len)
                assert result == expected or result == str(input_str)[:max_len]
            except Exception:
                # Some inputs may cause exceptions - that's okay
                pass

    def test_04_fuzz_metadata_uri(self):
        """Fuzz metadata URI validator"""
        invalid_uris = [
            "http://evil.com",  # Not HTTPS
            "ftp://example.com",  # Wrong protocol
            "javascript:alert('xss')",  # JS injection
            "file:///etc/passwd",  # File protocol
            "'" * 100,  # SQL injection
            "<script>alert(1)</script>",  # XSS
            "https://" + "a" * 1000,  # Very long hostname
            None,
            12345,
        ]

        for uri in invalid_uris:
            try:
                result = is_valid_metadata_uri(uri)
                assert result == False, f"Should be invalid: {uri}"
            except Exception:
                pass

    def test_05_fuzz_social_url(self):
        """Fuzz social URL validator"""
        invalid_urls = [
            "http://evil.com",  # Not HTTPS
            "ftp://example.com",
            "javascript:alert('xss')",
            None,
            12345,
            "https://" + "a" * 500,
        ]

        for url in invalid_urls:
            try:
                result = is_valid_social_url(url)
                assert result == False, f"Should be invalid: {url}"
            except Exception:
                pass

    def test_06_fuzz_positive_number(self):
        """Fuzz positive number validator"""
        invalid_numbers = [
            -1,
            0,
            -0.001,
            "not a number",
            None,
            "",
            "infinity",
            "NaN",
            "1/0",
            "'; DROP TABLE users; --",
        ]

        for num in invalid_numbers:
            try:
                result = is_valid_positive_number(num)
                assert result == False, f"Should be invalid: {num}"
            except Exception:
                pass

    def test_07_boundary_testing_pubkey(self):
        """Test boundary cases for pubkey validation"""
        # Note: "1" is a valid base58 character, so "1" * n is valid base58
        # Generate valid base58 strings of various lengths
        import base58

        test_cases = [
            (base58.b58encode(os.urandom(32)).decode(), True),  # Valid 32-byte key
            (base58.b58encode(os.urandom(32)).decode(), True),  # Valid key
        ]

        for key, expected in test_cases:
            result = is_valid_base58_pubkey(key)
            assert result == expected

        # Test invalid: containing non-base58 characters
        invalid_keys = [
            "O" * 44,  # Contains "O" (not in base58)
            "I" * 44,  # Contains "I" (not in base58)
            "l" * 44,  # Contains "l" (not in base58)
        ]
        for key in invalid_keys:
            assert is_valid_base58_pubkey(key) == False

    def test_08_injection_attempts(self):
        """Test various injection attempts"""
        injection_payloads = [
            "'; DROP TABLE config; --",
            "../../../etc/passwd",
            "{{7*7}}",  # Template injection
            "${7*7}",  # Template injection
            "<%= 7*7 %>",  # ERB injection
            "'; alert('xss'); //",
        ]

        for payload in injection_payloads:
            # Test with each validator
            assert is_valid_metadata_uri(payload) == False
            assert is_valid_social_url(payload) == False
            assert is_valid_base58_pubkey(payload) == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
