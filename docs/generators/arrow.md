# Arrow Generators

## Overview

Two generators emit [Apache Arrow](https://arrow.apache.org/) schemas from
`@Schema` classes, for use by Parquet readers/writers:

- **`arrow_rust`** (`ArrowRustGenerator`) — one `.rs` file per schema with a
  `pub fn <schema>_arrow_schema() -> arrow::datatypes::Schema` builder
  function, plus a `mod.rs` index. Targets [`arrow-rs`](https://docs.rs/arrow/).
- **`arrow_python`** (`ArrowPythonGenerator`) — one `.py` module per schema
  with a top-level `SCHEMA = pa.schema([...])`, plus an `__init__.py` that
  re-exports every schema as `<NAME>_SCHEMA`. Targets [`pyarrow`](https://arrow.apache.org/docs/python/).

Both generators resolve every field through the same finite
`FieldType -> Arrow DataType` mapping table, so the two outputs can never
silently diverge on what a given field maps to.

## Variants

Each entry in a schema's `class Variants:` block gets its own scoped Arrow
schema alongside the base one — `pub fn <schema>_<variant>_arrow_schema()`
(Rust) and `<VARIANT>_SCHEMA` (Python), containing only that variant's
fields. The Python index (`__init__.py`) re-exports every schema's base and
variant schemas under a name namespaced by schema (`<NAME>_SCHEMA`,
`<NAME>_<VARIANT>_SCHEMA`) so multiple schemas sharing an index never
collide on a bare `SCHEMA`.

## Quick start

```python
# schemas/order.py
from datetime import datetime
from schema_gen import Schema, Field

@Schema
class Order:
    """A single customer order."""

    id: int = Field(description="Order id")
    ts: datetime = Field(description="Order time")
    oi_change_5m: dict[str, float] | None = Field(default=None)
```

```bash
schema-gen generate --target arrow_rust --target arrow_python
```

Generated `generated/arrow_rust/order.rs`:

```rust
// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
use std::sync::Arc;

use arrow::datatypes::{DataType, Field, Schema, TimeUnit};

pub fn order_arrow_schema() -> Schema {
    let fields: Vec<Field> = vec![
        Field::new("id", DataType::Int64, false),
        Field::new("ts", DataType::Timestamp(TimeUnit::Microsecond, Some("UTC".into())), false),
        Field::new("oi_change_5m", DataType::LargeUtf8, true),
    ];
    Schema::new(fields)
}
```

Generated `generated/arrow_python/order_arrow.py`:

```python
import pyarrow as pa

SCHEMA = pa.schema(
    [
        pa.field('id', pa.int64(), nullable=False),
        pa.field('ts', pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field('oi_change_5m', pa.large_string(), nullable=True),
    ],
)
```

## Type mapping

| USR `FieldType`                | Arrow type                              |
| ------------------------------- | ---------------------------------------- |
| `STRING`                        | `Utf8`                                   |
| `BOOLEAN`                       | `Boolean`                                |
| `INTEGER`                       | `Int64`                                  |
| `FLOAT`                         | `Float64`                                |
| `DATETIME`                      | `Timestamp(<unit>, "UTC")` — see below   |
| `DATE`                          | `Date32`                                 |
| `TIME`                          | `Time64(Microsecond)`                    |
| `BYTES`                         | `Binary`                                 |
| `UUID`, `JSON`, `LITERAL`, `ENUM` | `Utf8` (Arrow has no native type for these — carried as strings) |
| `DECIMAL`                       | `Decimal128(precision, scale)` — see below |
| `LIST` / `SET` / `FROZENSET`    | `List(<item type>)` (recurses on `inner_type`; `Utf8` items if untyped) |
| `TUPLE`                         | `List(<first member's type>)` (best-effort — Arrow has no tuple type) |
| `DICT`                          | `LargeUtf8` (JSON-serialized string) by default — see below |
| every other `FieldType`         | **raises `ValueError`** — no silent lossy fallback |

`OPTIONAL` is not a distinct Arrow type: `Field.optional` (or a nested
`FieldType.OPTIONAL` wrapper) controls `nullable=` on the emitted `Field`;
the wrapped type resolves normally.

### Why `DICT` defaults to `LargeUtf8`, not `Map`

A `dict[str, T]` field could in principle map to Arrow's native
`Map(Utf8, T)` type. The default here is instead a JSON-serialized
`LargeUtf8` string column, matching the first real consumer
(tradingcore's Parquet export, `src/sink/backtest.rs`): CME per-strike
dict fields can average ~100KB/row of JSON, and a single day's export
(~40k rows) produces several GB of text — well past the 2GB i32-offset
ceiling of plain `Utf8`, hence `LargeUtf8` (i64 offsets) specifically,
not just "a string type". See tradingcore#697.

If you want a native, decodable `Map(Utf8, T)` instead — only possible
when the value type is concrete (`dict[str, T]`, not a bare/untyped
`dict`) — opt in per field:

```python
oi_change_5m: dict[str, float] | None = Field(
    default=None, arrow={"dict_as": "map"}
)
```

### Timestamp unit override

`DATETIME` fields default to microsecond precision. Real schemas often mix
granularities in one struct (e.g. a nanosecond-precision primary
`timestamp` alongside millisecond-precision "last tick time" fields) —
override per field:

```python
ts: datetime = Field(arrow={"timestamp_unit": "nanosecond"})
```

Valid units: `"second"`, `"millisecond"`, `"microsecond"`, `"nanosecond"`.
An invalid unit logs a warning and falls back to microsecond.

### Decimal precision/scale override

`DECIMAL` fields default to `Decimal128(38, 9)`. Override per field:

```python
notional: Decimal = Field(arrow={"precision": 18, "scale": 4})
```

## Nullability

Optional fields (`T | None`, `Optional[T]`) emit `nullable=true`. Required
fields emit `nullable=false`.

## Metadata passthrough

Schema-level and field-level `description=` land in Arrow metadata —
`Schema.with_metadata({"description": ...})` (Rust) / `pa.schema(...,
metadata={'description': ...})` (Python) at the schema level, and
`metadata={'description': ...}` on the individual `pa.field(...)` calls
(Python) or a `//` doc comment immediately above the field (Rust).

## Field-name identifier safety

Arrow itself places no constraint on column names, but downstream tooling
does — `pandas.itertuples()` silently renames columns that aren't valid
Python identifiers, for example. A field name that isn't a valid
Python/Rust identifier logs a warning (not an error) during generation.

## Determinism

Field order in the generated `Schema`/`pa.schema([...])` always follows
the `@Schema` class's declaration order — never a hash- or dict-derived
order — so re-running `schema-gen generate` against an unchanged source
schema produces byte-identical output.
