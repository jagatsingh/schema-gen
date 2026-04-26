"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: CanonicalOrder
Generator: schema-gen Pathway generator

To regenerate this file, run:
    schema-gen generate --target pathway

Changes to this file will be overwritten.
"""

import pathway as pw


class CanonicalOrder(pw.Table):
    """
    Order placed against the matching engine.

Carries the instrument identifier, the side (BUY/SELL), and an optional
client-supplied tag. Used as a fixture for cross-generator output
stability tests.
    """
    instrument: pw.ColumnExpression  # str  # Exchange-prefixed symbol
    quantity: pw.ColumnExpression  # int  # Number of contracts
    price: pw.ColumnExpression  # float  # Limit price
    side: pw.ColumnExpression  # str  # Buy or sell
    tag: pw.ColumnExpression  # str  # Optional client tag
    metadata: pw.ColumnExpression  # dict  # Free-form metadata
    fills: pw.ColumnExpression  # list[float]  # Per-fill prices (FIFO)