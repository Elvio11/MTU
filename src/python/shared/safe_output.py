"""
Safe Output Utilities - Handles encoding issues across platforms.
Ensures emoji and special characters are displayed correctly.
"""

import sys
import os


def safe_print(*args, **kwargs):
    """Print with safe encoding for all platforms.

    Replaces:
        → (RIGHTWARDS ARROW) -> ->
        ← (LEFTWARDS ARROW) -> <-
        ✅ (CHECK MARK) -> [OK]
        ❌ (CROSS MARK) -> [X]
        🚨 (POLICE CAR LIGHT) -> [!]
    """
    replacements = {
        "→": "->",
        "←": "<-",
        "✅": "[OK]",
        "❌": "[X]",
        "🚨": "[!]",
        "📊": "[STATS]",
        "💰": "[MONEY]",
        "🔴": "[RED]",
        "🟢": "[GREEN]",
        "⚠️": "[WARN]",
    }

    import io
    from functools import reduce

    # Process all string arguments
    safe_args = []
    for arg in args:
        if isinstance(arg, str):
            result = arg
            for old, new in replacements.items():
                result = result.replace(old, new)
            safe_args.append(result)
        else:
            safe_args.append(arg)

    # Use a fallback encoding approach
    try:
        print(*safe_args, **kwargs)
    except (UnicodeEncodeError, AttributeError):
        # Fallback: convert to ASCII-safe string
        ascii_args = []
        for arg in safe_args:
            if isinstance(arg, str):
                # Force ASCII, replacing non-printable chars
                ascii_args.append(arg.encode("ascii", "replace").decode("ascii"))
            else:
                ascii_args.append(arg)
        print(*ascii_args, **kwargs)


def safe_str(text: str) -> str:
    """Convert string to platform-safe format."""
    replacements = {
        "→": "->",
        "←": "<-",
        "✅": "[OK]",
        "❌": "[X]",
        "🚨": "[!]",
        "📊": "[STATS]",
        "💰": "[MONEY]",
        "🔴": "[RED]",
        "🟢": "[GREEN]",
        "⚠️": "[WARN]",
    }

    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def setup_console():
    """Setup console for Unicode output on Windows."""
    if sys.platform == "win32":
        try:
            # Try to set UTF-8 mode on Windows
            import codecs

            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, errors="replace")
        except Exception:
            pass


# Auto-setup when imported
setup_console()
