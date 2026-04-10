# Rust Serde Generator

## Overview

The Rust generator emits idiomatic Rust modules for each `@Schema` class,
using the mainstream Rust serialization stack: [`serde`](https://serde.rs/)
+ [`serde_json`](https://docs.rs/serde_json/), optional
[`schemars::JsonSchema`](https://docs.rs/schemars/) derives, and
domain-appropriate types from `chrono`, `uuid`, and `rust_decimal`. Output
is one `.rs` file per schema, a shared `common.rs` for enums referenced by
more than one schema, a `lib.rs` index, and a minimal `Cargo.toml`. The
crate is configurable via `Config.rust`.

## Quick start

```python
# schemas/order.py
from schema_gen import Schema, Field

@Schema
class Order:
    """A single customer order."""

    id: int = Field(rust={"type": "u64"}, description="Order id")
    quantity: int = Field(rust={"type": "u32"}, description="Units")
    note: str | None = Field(default=None)
```

```bash
schema-gen generate
```

Generated `generated/rust/order.rs`:

```rust
// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
use serde::{Deserialize, Serialize};
use schemars::JsonSchema;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Order {
    /// Order id
    pub id: u64,
    /// Units
    pub quantity: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}
```

Generated `generated/rust/lib.rs`:

```rust
// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
pub mod order;

pub use order::*;
```

Generated `generated/rust/Cargo.toml`:

```toml
[package]
name = "schema-gen-generated-contracts"
version = "0.0.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
chrono = { version = "0.4", features = ["serde"] }
schemars = "0.8"
```

## Field type mapping

| Python type                  | Rust type                       |
|-----------------------------|---------------------------------|
| `str`                        | `String`                        |
| `int`                        | `i64` (override-able)           |
| `float`                      | `f64` (override-able)           |
| `bool`                       | `bool`                          |
| `bytes`                      | `Vec<u8>`                       |
| `datetime`                   | `chrono::DateTime<chrono::Utc>` |
| `date`                       | `chrono::NaiveDate`             |
| `time`                       | `chrono::NaiveTime`             |
| `UUID`                       | `uuid::Uuid`                    |
| `Decimal`                    | `rust_decimal::Decimal`         |
| `dict[str, Any]`             | `serde_json::Value`             |
| `dict[str, T]`               | `HashMap<String, T>`            |
| `list[T]` / `set[T]`         | `Vec<T>`                        |
| `tuple[A, B, ...]`           | `(A, B, ...)`                   |
| `Optional[T]`                | `Option<T>` (+ `skip_serializing_if`) |
| `Union[...]` (plain)         | `serde_json::Value` (warning)   |
| `Annotated[Union, Field(discriminator=...)]` | `#[serde(tag = "...")]` enum |
| `Literal["a", "b"]`          | `String` (v1)                   |
| `Enum` subclass              | enum reference (emitted in `common.rs`) |
| Nested `@Schema`             | struct reference                |

## `SerdeMeta` inner class

`SerdeMeta` is the Rust analog of `PydanticMeta`. It is attached either to
a `@Schema` class or to an `Enum` subclass, and controls derives, imports,
and raw code injection.

### `imports`

Extra `use` lines rendered at the top of the file.

```python
class SerdeMeta:
    imports = ["use std::collections::BTreeMap;"]
```

### `derives`

Extra derive macros appended to the struct / enum derive list.

```python
class SerdeMeta:
    derives = ["Default", "Eq", "Hash"]
```

### `raw_code`

Verbatim Rust code appended after the generated struct or enum. Typically
used for `impl` blocks with domain methods.

```python
class SerdeMeta:
    raw_code = """
impl Order {
    pub fn total(&self, price: f64) -> f64 { price * self.quantity as f64 }
}
"""
```

### `deny_unknown_fields`

Defaults to `True`. Set to `False` to opt out of
`#[serde(deny_unknown_fields)]` on a per-struct basis.

```python
class SerdeMeta:
    deny_unknown_fields = False
```

### `rename_all`

Schema-level rename transform applied uniformly to every field (and every
inline enum in the schema). Must be one of: `lowercase`, `UPPERCASE`,
`PascalCase`, `camelCase`, `snake_case`, `SCREAMING_SNAKE_CASE`,
`kebab-case`, `SCREAMING-KEBAB-CASE`.

```python
class SerdeMeta:
    rename_all = "camelCase"
```

### `json_schema_derive`

Defaults to `True`. When `False`, the `schemars::JsonSchema` derive is
omitted.

```python
class SerdeMeta:
    json_schema_derive = False
```

## Per-field type overrides

Use `Field(rust={"type": "..."})` to pick a specific integer or float
width. The value is validated against Rust's built-in type whitelist;
invalid values log a warning and fall back to `i64` / `f64`.

```python
small: int = Field(rust={"type": "u8"})
id:    int = Field(rust={"type": "u64"})
ratio: float = Field(rust={"type": "f32"})
```

Valid integer types: `i8`, `i16`, `i32`, `i64`, `i128`, `isize`, `u8`,
`u16`, `u32`, `u64`, `u128`, `usize`. Valid float types: `f32`, `f64`.

## Enums

### Wire-format preservation

By default the Rust generator emits one `#[serde(rename = "<value>")]`
per variant, using the actual Python enum value. This preserves mixed
casing on the wire exactly as written in Python — e.g. `NSE = "NSE"`
stays `"NSE"` and `buy = "buy"` stays `"buy"` inside the same enum.

```python
from enum import Enum

class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
```

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize, JsonSchema)]
pub enum Exchange {
    #[serde(rename = "NSE")]
    NSE,
    #[serde(rename = "BSE")]
    BSE,
}
```

### Enum-level `SerdeMeta`

Attach a `SerdeMeta` inner class to an `Enum` subclass to inject domain
methods on the generated Rust enum (and/or extra derives).

```python
class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

    class SerdeMeta:
        derives = ["Eq", "Hash"]
        raw_code = """
impl OrderStatus {
    pub fn is_terminal(&self) -> bool {
        matches!(self, OrderStatus::Filled | OrderStatus::Cancelled)
    }
}
"""
```

### Overriding the rename strategy

Schema-level `SerdeMeta.rename_all` switches the enum to a uniform
`#[serde(rename_all = "...")]` attribute instead of per-variant renames.

## Discriminated unions

Tagged enums are emitted for fields annotated with
`Annotated[Union[...], Field(discriminator="<tag>")]` where every union
member is a `@Schema` class with a matching `Literal["..."]` tag field.

```python
from typing import Annotated, Literal, Union
from schema_gen import Schema, Field

@Schema
class MarketLeg:
    type: Literal["market"]
    qty: int

@Schema
class LimitLeg:
    type: Literal["limit"]
    qty: int
    price: float

@Schema
class Order:
    leg: Annotated[Union[MarketLeg, LimitLeg], Field(discriminator="type")]
```

Emits a helper tagged enum named `<Struct><FieldCamel>` (here
`OrderLeg`):

```rust
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "type")]
pub enum OrderLeg {
    #[serde(rename = "market")]
    Market(MarketLeg),
    #[serde(rename = "limit")]
    Limit(LimitLeg),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Order {
    pub leg: OrderLeg,
}
```

Plain `Union[A, B]` without a discriminator is emitted as
`serde_json::Value` and logs a warning. See the [Known limitations](#known-limitations)
section.

## Variants

`class Variants:` blocks still work: each variant is emitted as a separate
struct named `<Schema><Variant>` (PascalCase). When the variant's fields
are a strict subset of the base and every missing base field is
`Option<T>` or has an explicit default, schema-gen also emits a
`From<Variant> for Base` impl.

```python
@Schema
class User:
    id: int
    name: str
    email: str | None = Field(default=None)

    class Variants:
        create_request = ["name"]
```

```rust
pub struct User { pub id: i64, pub name: String, pub email: Option<String> }
pub struct UserCreateRequest { pub name: String }
// From impl only emitted when missing fields are safely fillable.
```

The `From` impl is suppressed when a missing base field is non-optional
and has no default, so generated code always compiles.

## `Config.rust` options

All keys are optional. Defaults preserve the quick-start output.

| Key                   | Default                               | Description |
|----------------------|---------------------------------------|-------------|
| `json_schema_derive` | `True`                                | Emit `#[derive(JsonSchema)]`. |
| `deny_unknown_fields`| `True`                                | Emit `#[serde(deny_unknown_fields)]`. |
| `rename_all`         | unset                                 | Global rename transform (see whitelist above). |
| `crate_name`         | `"schema-gen-generated-contracts"`    | `[package] name` in `Cargo.toml`. |
| `crate_version`      | `"0.0.0"`                             | `[package] version`. |
| `edition`            | `"2021"`                              | `[package] edition`. |
| `extra_deps`         | `{}`                                  | Extra `[dependencies]` (mapping crate name → version string). |
| `emit_cargo_toml`    | `True`                                | Set to `False` to skip `Cargo.toml` emission. |

```python
config = Config(
    targets=["rust"],
    rust={
        "crate_name": "my-contracts",
        "crate_version": "0.1.0",
        "edition": "2021",
        "extra_deps": {"thiserror": "1"},
        "json_schema_derive": True,
        "deny_unknown_fields": True,
        "emit_cargo_toml": True,
    },
)
```

## Shared enums in `common.rs`

When multiple schemas reference the same `Enum` subclass, schema-gen
emits its definition once in `generated/rust/common.rs` instead of
duplicating it across every file. The individual schema files pull it in
via `use super::common::*;` (wired through `lib.rs`). This keeps generated
crates compile-clean and avoids "duplicate definition" errors when enums
are shared across contract modules.

## Cross-module `use` statements

When a schema references another `@Schema` class generated in a sibling
file, schema-gen automatically emits `use super::<module>::<Type>;` at
the top of the referencing file. No manual wiring is needed.

## Known limitations

- **Plain unions** without a discriminator fall back to
  `serde_json::Value` and log a warning. Use
  `Annotated[Union[...], Field(discriminator="...")]` whenever possible.
  Full untagged-union support is tracked in
  [jagatsingh/schema-gen#18](https://github.com/jagatsingh/schema-gen/issues/18).
- **`Literal["a", "b"]`** is mapped to `String` in v1 — the string-enum
  lowering is a follow-up.
- **Nested `Optional` inside collections** (`list[Optional[T]]`) is not
  special-cased; it lowers to `Vec<Option<T>>` only when the USR layer
  retains the `Optional` wrapper on the inner type.
- **`dict[str, T]`** always lowers to
  `HashMap<String, serde_json::Value>` — the value type is not yet
  threaded through USR. Tracked with
  [jagatsingh/schema-gen#19](https://github.com/jagatsingh/schema-gen/issues/19).
- **Pydantic / Zod discriminated-union emit** is not yet implemented;
  only the Rust side honors `Field(discriminator=...)` today. Tracked
  in [jagatsingh/schema-gen#20](https://github.com/jagatsingh/schema-gen/issues/20).
