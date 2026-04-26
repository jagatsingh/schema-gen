"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: CanonicalOrder
Generator: schema-gen SQLAlchemy generator

To regenerate this file, run:
    schema-gen generate --target sqlalchemy

Changes to this file will be overwritten.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ._base import Base


class CanonicalOrder(Base):
    """Order placed against the matching engine.

    Carries the instrument identifier, the side (BUY/SELL), and an optional
    client-supplied tag. Used as a fixture for cross-generator output
    stability tests.
    """
    __tablename__ = "canonical_order"

    instrument: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column()
    price: Mapped[float] = mapped_column()
    side: Mapped[str] = mapped_column(String(20))
    tag: Mapped[str | None] = mapped_column(Text)
    metadata: Mapped[str] = mapped_column(String(255))
    fills: Mapped[str] = mapped_column(String(255))