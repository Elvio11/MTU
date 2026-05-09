import re
from typing import Optional


def is_valid_base58_pubkey(key: str) -> bool:
    """Validate Solana public key (base58, 32-44 chars)"""
    if not key or len(key) < 32 or len(key) > 44:
        return False
    try:
        import base58

        decoded = base58.b58decode(key)
        return len(decoded) == 32
    except Exception:
        return False


def truncate_string(s: str, max_length: int) -> str:
    """Truncate string to max_length per Section 4.2"""
    if not s:
        return ""
    return s[:max_length]


def is_valid_metadata_uri(uri: str) -> bool:
    """Validate metadata URI: HTTPS only per Section 4.2"""
    if not uri:
        return False
    return uri.startswith("https://") and not uri.startswith("http://")


def is_valid_social_url(url: str) -> bool:
    """Validate social URLs against allowlist per Section 4.2"""
    if not url:
        return False
    allowed_domains = ["twitter.com", "x.com", "t.me", "telegram.me"]
    for domain in allowed_domains:
        if domain in url.lower():
            return True
    return False


def is_valid_positive_number(value: any) -> bool:
    """Validate numeric fields are finite positive numbers per Section 4.2"""
    if value is None:
        return False
    try:
        num = float(value)
        return num > 0 and not (num != num)  # NaN check
    except (ValueError, TypeError):
        return False


def validate_solana_pubkey(key: str) -> bool:
    """Alias for is_valid_base58_pubkey"""
    return is_valid_base58_pubkey(key)
