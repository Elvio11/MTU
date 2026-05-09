from pydantic import BaseModel, Field, field_validator
from typing import Optional


class PumpPortalTokenPayload(BaseModel):
    mint: str
    name: Optional[str] = Field(None, max_length=100)
    symbol: Optional[str] = Field(None, max_length=20)
    uri: Optional[str] = None
    initialBuy: float = 0.0
    marketCapSol: float
    bondingCurveKey: Optional[str] = None
    vSolInBondingCurve: float
    creator: Optional[str] = None
    bondingCurveProgress: float = 0.0

    @field_validator("mint", "creator", "bondingCurveKey")
    @classmethod
    def validate_base58(cls, v: str) -> Optional[str]:
        if v is None:
            return None
        import base58

        try:
            decoded = base58.b58decode(v)
            if len(decoded) != 32:
                raise ValueError(f"Must be 32 bytes, got {len(decoded)}")
        except Exception:
            raise ValueError("Must be a valid base58 public key")
        return v

    @field_validator("uri")
    @classmethod
    def validate_https_uri(cls, v: str) -> Optional[str]:
        if v is None:
            return None
        if not v.startswith("https://"):
            raise ValueError("Metadata URI must use HTTPS")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        from src.python.shared.validators import truncate_string

        return truncate_string(v, 100)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        from src.python.shared.validators import truncate_string

        return truncate_string(v, 20)
