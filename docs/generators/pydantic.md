# Pydantic Generator

## Overview

The Pydantic generator emits [Pydantic v2](https://docs.pydantic.dev/) models
(`BaseModel` subclasses) for each `@Schema` class and its variants. It
honors `PydanticMeta` inner classes on both `@Schema` classes and `Enum`
subclasses, and wires top-level `Config.pydantic` settings into the
generated `model_config = ConfigDict(...)` block.

## `Config.pydantic` options

Top-level `Config.pydantic` keys are now threaded into every generated
model's `ConfigDict`. Only the keys below are honored — any unrecognized
keys are silently ignored so typos don't spuriously enable
`model_config` on otherwise default schemas.

| Key                    | Type        | Description |
|------------------------|-------------|-------------|
| `extra`                | `str`       | Pydantic's extra-field policy. Typical values: `"forbid"`, `"allow"`, `"ignore"`. |
| `validate_assignment`  | `bool`      | Re-run validation when an attribute is assigned after construction. |
| `frozen`               | `bool`      | Make models immutable (`__hash__` auto-generated). |
| `strict`               | `bool`      | Enable strict-mode coercion rules. |
| `str_strip_whitespace` | `bool`      | Auto-strip whitespace from all string fields. |
| `populate_by_name`     | `bool`      | Allow populating fields by their declared name even when an alias is set. |
| `serialize_by_alias`   | `bool`      | Serialize using alias keys by default (affects `model_dump()` / `model_dump_json()`). Auto-enabled when any field has `alias=`. |

String values are properly `repr()`-escaped, so `extra="forbid"` emits
`extra='forbid'` in the generated `ConfigDict(...)`.

```python
from schema_gen import Config

config = Config(
    targets=["pydantic"],
    pydantic={
        "extra": "forbid",
        "validate_assignment": True,
        "frozen": False,
        "strict": True,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    },
)
```

The generator combines these with its default
`from_attributes=True`, producing e.g.:

```python
class User(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra='forbid',
        validate_assignment=True,
        strict=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )
    ...
```

## Field aliases (issue #108)

`Field(alias="<wire-key>")` lets a schema author keep one Python
attribute name while serializing under a different wire-format key:

```python
@Schema
class StrategyDef:
    coalesce_reasoning: str | None = Field(
        default=None,
        alias="_coalesce_reasoning",
    )
```

The Pydantic generator emits `Field(alias="_coalesce_reasoning")` and
auto-enables both `populate_by_name=True` (so the model accepts either
the alias or the Python attribute name on input) and `serialize_by_alias=True`
(so `model_dump()` / `model_dump_json()` return alias keys by default,
without needing `by_alias=True` at every call site — issue #111).
Both flags are added on demand — schemas without any aliased fields don't acquire them.

## `PydanticMeta` on schemas

`PydanticMeta` inner classes inject custom validators, instance methods,
and imports into the generated base model (variants never inherit custom
code). See the [Schema Format](../schema-format.md#custom-code-injection)
document for the full syntax.

Supported attributes:

| Attribute  | Description |
|-----------|-------------|
| `imports` | Extra `import` lines emitted at the top of the file. |
| `raw_code`| Verbatim code appended inside the class body (typically `@field_validator` blocks). |
| `methods` | Instance methods appended inside the class body. |
| `validators` | Reserved for future validator-specific emission. |

## `PydanticMeta` on enums

`PydanticMeta` can also be attached to `Enum` subclasses. Today the
generator honors the `methods` attribute, which injects domain methods
directly into the generated Python enum class body. This keeps Python
and Rust side-by-side in sync when you use enum-level `SerdeMeta` for
the Rust target.

> **Python 3.12+**: Inner classes inside `str, Enum` or `StrEnum` are
> treated as enum members, which causes errors. Wrap with
> `enum.nonmember()` to prevent this.

```python
from enum import Enum, nonmember

class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

    PydanticMeta = nonmember(
        type(
            "PydanticMeta",
            (),
            {
                "methods": """
    def is_terminal(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED)
"""
            },
        )
    )
```

Generated:

```python
class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED)
```
