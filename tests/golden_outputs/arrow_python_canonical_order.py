"""AUTO-GENERATED FILE - DO NOT EDIT MANUALLY.

pyarrow schema for `CanonicalOrder`, generated from its USR definition.
"""

import pyarrow as pa

SCHEMA = pa.schema(
    [
        pa.field('instrument', pa.string(), nullable=False, metadata={'description': 'Exchange-prefixed symbol'}),
        pa.field('quantity', pa.int64(), nullable=False, metadata={'description': 'Number of contracts'}),
        pa.field('price', pa.float64(), nullable=False, metadata={'description': 'Limit price'}),
        pa.field('side', pa.string(), nullable=False, metadata={'description': 'Buy or sell'}),
        pa.field('tag', pa.string(), nullable=True, metadata={'description': 'Optional client tag'}),
        pa.field('metadata', pa.large_string(), nullable=False, metadata={'description': 'Free-form metadata'}),
        pa.field('fills', pa.list_(pa.field('item', pa.float64(), nullable=True)), nullable=False, metadata={'description': 'Per-fill prices (FIFO)'}),
    ],
    metadata={'description': 'Order placed against the matching engine.\n\nCarries the instrument identifier, the side (BUY/SELL), and an optional\nclient-supplied tag. Used as a fixture for cross-generator output\nstability tests.'},
)
