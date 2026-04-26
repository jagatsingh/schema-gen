"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: CanonicalOrder
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional


class CanonicalSide(str, Enum):
    """Two-sided trade direction."""
    BUY = "buy"
    SELL = "sell"

class CanonicalOrder(BaseModel):
    """Order placed against the matching engine.

    Carries the instrument identifier, the side (BUY/SELL), and an optional
    client-supplied tag. Used as a fixture for cross-generator output
    stability tests.
    """
    instrument: str = Field(..., description="Exchange-prefixed symbol")
    quantity: int = Field(..., description="Number of contracts")
    price: float = Field(..., description="Limit price")
    side: CanonicalSide = Field(..., description="Buy or sell")
    tag: Optional[str] = Field(default=None, description="Optional client tag")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Free-form metadata")
    fills: list[float] = Field(default_factory=list, description="Per-fill prices (FIFO)")