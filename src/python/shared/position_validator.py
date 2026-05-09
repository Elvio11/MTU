from typing import Optional
from decimal import Decimal


class PositionValidator:
    """Validates position sizes and trade parameters"""

    def __init__(
        self,
        max_position_size_sol: float = 0.15,
        min_position_size_sol: float = 0.0001,  # Match config.yaml position_size_sol
        max_slippage_bps: int = 2000,
    ):
        self.max_position_size_sol = Decimal(str(max_position_size_sol))
        self.min_position_size_sol = Decimal(str(min_position_size_sol))
        self.max_slippage_bps = max_slippage_bps

    def validate_position_size(self, size_sol: float) -> tuple[bool, str]:
        """Validate position size is within limits"""
        size = Decimal(str(size_sol))

        if size > self.max_position_size_sol:
            return (
                False,
                f"Position size {size_sol} SOL exceeds max {self.max_position_size_sol} SOL",
            )

        if size < self.min_position_size_sol:
            return (
                False,
                f"Position size {size_sol} SOL below min {self.min_position_size_sol} SOL",
            )

        return True, "OK"

    def validate_slippage(self, slippage_bps: int) -> tuple[bool, str]:
        """Validate slippage is within limits"""
        if slippage_bps > self.max_slippage_bps:
            return (
                False,
                f"Slippage {slippage_bps} bps exceeds max {self.max_slippage_bps} bps",
            )

        return True, "OK"

    def validate_token_address(self, address: str) -> tuple[bool, str]:
        """Validate token address is valid base58"""
        if not address:
            return False, "Token address is empty"

        # Basic validation - should be base58 and around 32-44 chars
        if len(address) < 32 or len(address) > 44:
            return False, f"Invalid token address length: {len(address)}"

        # Check for valid base58 characters
        import re

        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]+$", address):
            return False, "Token address contains invalid characters"

        return True, "OK"

    def calculate_slippage_tier(self, attempt: int) -> int:
        """Get slippage based on retry attempt"""
        slippage_tiers = [1000, 1500, 2000]  # 10%, 15%, 20%
        return slippage_tiers[min(attempt, len(slippage_tiers) - 1)]

    def validate_trade_params(
        self, position_size_sol: float, slippage_bps: int, token_address: str
    ) -> tuple[bool, str]:
        """Validate all trade parameters at once"""
        # Validate position size
        valid, msg = self.validate_position_size(position_size_sol)
        if not valid:
            return False, msg

        # Validate slippage
        valid, msg = self.validate_slippage(slippage_bps)
        if not valid:
            return False, msg

        # Validate token address
        valid, msg = self.validate_token_address(token_address)
        if not valid:
            return False, msg

        return True, "All parameters valid"


# Global validator instance
_validator: Optional[PositionValidator] = None


def get_position_validator(
    max_position_size_sol: float = 0.15,
    min_position_size_sol: float = 0.0001,  # Match config.yaml position_size_sol
    max_slippage_bps: int = 2000,
) -> PositionValidator:
    """Get or create the global position validator"""
    global _validator
    if _validator is None:
        _validator = PositionValidator(
            max_position_size_sol, min_position_size_sol, max_slippage_bps
        )
    return _validator
