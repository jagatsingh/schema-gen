"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: CanonicalOrder
Generator: schema-gen TypedDict generator

To regenerate this file, run:
    schema-gen generate --target typeddict

Changes to this file will be overwritten.
"""

from typing_extensions import TypedDict, NotRequired
from typing import Any, Dict, List, Literal, Union


class CanonicalOrder(TypedDict):
    """
    Order placed against the matching engine.

Carries the instrument identifier, the side (BUY/SELL), and an optional
client-supplied tag. Used as a fixture for cross-generator output
stability tests.
    """
    instrument: str  # Exchange-prefixed symbol
    quantity: int  # Number of contracts
    price: float  # Limit price
    side: str  # Buy or sell
    tag: NotRequired[str]  # Optional client tag
    metadata: dict[str, Any]  # Free-form metadata
    fills: list[float]  # Per-fill prices (FIFO)