import hmac
import hashlib
import time
from typing import Optional


def generate_otp(seed: str, timestamp: Optional[int] = None) -> str:
    """Generate HMAC-signed OTP per Section 4.3"""
    ts = timestamp or int(time.time())
    # 30-second window
    message = str(ts // 30).encode()
    return hmac.new(seed.encode(), message, hashlib.sha256).hexdigest()[:8]


def verify_otp(seed: str, otp: str, window: int = 1) -> bool:
    """Verify OTP with time window tolerance"""
    current_ts = int(time.time())
    current_window = current_ts // 30
    for delta in range(-window, window + 1):
        test_window = current_window + delta
        test_otp = hmac.new(
            seed.encode(), str(test_window).encode(), hashlib.sha256
        ).hexdigest()[:8]
        if hmac.compare_digest(test_otp, otp):
            return True
    return False
