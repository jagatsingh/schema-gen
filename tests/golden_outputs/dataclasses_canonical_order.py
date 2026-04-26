"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: CanonicalOrder
Generator: schema-gen Dataclasses generator

To regenerate this file, run:
    schema-gen generate --target dataclasses

Changes to this file will be overwritten.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Any, Dict, List, Literal, Optional, Union


@dataclass
class CanonicalOrder:
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
    tag: str = None  # Optional client tag
    metadata: dict[str, Any] = field(default_factory=dict)  # Free-form metadata
    fills: list[float] = field(default_factory=list)  # Per-fill prices (FIFO)