"""Snapshot/golden-file tests locking generator output for downstream consumers.

Each generator is run against a single canonical schema that exercises the
features most downstream consumers care about (multi-line class docstring,
enum, optional, list, dict, union, primitive types). The output is compared
byte-by-byte against a stored golden file under ``tests/golden_outputs/``.

**Purpose** — a downstream regen (tradingcore, tradingutils, trading-platform
or any other consumer) bumps schema-gen and re-runs the generator. If
schema-gen accidentally changes a single space, comma, or blank line in the
output, downstream PRs balloon with hundreds of cosmetic diffs that drown
the actual change. These tests fail loudly when output changes so the
maintainer sees the drift *here* and can either roll it back or update the
golden file deliberately.

**To intentionally update the golden files** after a deliberate format
change::

    UPDATE_GOLDEN=1 uv run pytest tests/test_generator_output_stability.py

Then commit the updated ``tests/golden_outputs/*`` along with the source
change so reviewers see exactly what downstream regenerations will see.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.avro_generator import AvroGenerator
from schema_gen.generators.dataclasses_generator import DataclassesGenerator
from schema_gen.generators.graphql_generator import GraphQLGenerator
from schema_gen.generators.jackson_generator import JacksonGenerator
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.kotlin_generator import KotlinGenerator
from schema_gen.generators.pathway_generator import PathwayGenerator
from schema_gen.generators.protobuf_generator import ProtobufGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
from schema_gen.generators.typeddict_generator import TypedDictGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

GOLDEN_DIR = Path(__file__).parent / "golden_outputs"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


# -----------------------------------------------------------------------
# Canonical schema — exercises the features downstream consumers care about
# -----------------------------------------------------------------------


class CanonicalSide(str, Enum):
    """Two-sided trade direction."""

    BUY = "buy"
    SELL = "sell"


@Schema
class CanonicalOrder:
    """Order placed against the matching engine.

    Carries the instrument identifier, the side (BUY/SELL), and an optional
    client-supplied tag. Used as a fixture for cross-generator output
    stability tests.
    """

    instrument: str = Field(description="Exchange-prefixed symbol")
    quantity: int = Field(description="Number of contracts")
    price: float = Field(description="Limit price")
    side: CanonicalSide = Field(description="Buy or sell")
    tag: str | None = Field(default=None, description="Optional client tag")
    metadata: dict = Field(default_factory=dict, description="Free-form metadata")
    fills: list[float] = Field(
        default_factory=list, description="Per-fill prices (FIFO)"
    )


def _parse_canonical():
    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(CanonicalOrder)
    return SchemaParser().parse_schema(CanonicalOrder)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _golden_path(name: str) -> Path:
    return GOLDEN_DIR / name


def _check_or_update(name: str, actual: str) -> None:
    """Compare ``actual`` against the stored golden file.

    Writes the file when ``UPDATE_GOLDEN=1`` is set in the environment,
    otherwise asserts byte-equality and produces a diff-friendly message.
    """
    path = _golden_path(name)
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
        return

    if not path.exists():
        pytest.fail(
            f"Golden file {path} does not exist. Run with UPDATE_GOLDEN=1 to create it."
        )

    expected = path.read_text()
    assert actual == expected, (
        f"\nGenerator output for {name} drifted from the golden snapshot.\n"
        f"If this change is INTENTIONAL, run:\n"
        f"    UPDATE_GOLDEN=1 uv run pytest tests/test_generator_output_stability.py\n"
        f"and commit the updated {path.relative_to(Path(__file__).parent.parent)}.\n"
        f"\nFirst differing region:\n"
        f"{_first_diff(expected, actual)}"
    )


def _first_diff(expected: str, actual: str) -> str:
    """Return a small context window around the first character that differs."""
    for i, (a, b) in enumerate(zip(expected, actual, strict=False)):
        if a != b:
            start = max(0, i - 40)
            end_e = min(len(expected), i + 40)
            end_a = min(len(actual), i + 40)
            return (
                f"  expected[{start}:{end_e}] = {expected[start:end_e]!r}\n"
                f"  actual[{start}:{end_a}]   = {actual[start:end_a]!r}"
            )
    if len(expected) != len(actual):
        return (
            f"  length differs: expected={len(expected)}, actual={len(actual)}\n"
            f"  expected tail: {expected[-80:]!r}\n"
            f"  actual tail:   {actual[-80:]!r}"
        )
    return "(strings are equal — assertion error is likely a test bug)"


# -----------------------------------------------------------------------
# Per-generator snapshot tests
# -----------------------------------------------------------------------

# Each entry: (golden_filename, generator_class). The schema is the same
# across all generators so the fixtures are directly comparable.
_GENERATORS = [
    ("pydantic_canonical_order.py", PydanticGenerator),
    ("rust_canonical_order.rs", RustGenerator),
    ("zod_canonical_order.ts", ZodGenerator),
    ("jsonschema_canonical_order.json", JsonSchemaGenerator),
    ("sqlalchemy_canonical_order.py", SqlAlchemyGenerator),
    ("dataclasses_canonical_order.py", DataclassesGenerator),
    ("typeddict_canonical_order.py", TypedDictGenerator),
    ("pathway_canonical_order.py", PathwayGenerator),
    ("avro_canonical_order.avsc", AvroGenerator),
    ("protobuf_canonical_order.proto", ProtobufGenerator),
    ("graphql_canonical_order.graphql", GraphQLGenerator),
    ("kotlin_canonical_order.kt", KotlinGenerator),
    ("jackson_canonical_order.java", JacksonGenerator),
]


@pytest.mark.parametrize("filename,generator_cls", _GENERATORS)
def test_generator_output_stable(filename: str, generator_cls: type) -> None:
    """Each generator must produce byte-identical output to the stored golden file.

    A failure here means a downstream consumer regenerating contracts will
    see a formatting diff. If the diff is intentional, regenerate the
    golden files via ``UPDATE_GOLDEN=1``.
    """
    schema = _parse_canonical()
    actual = generator_cls().generate_file(schema)
    _check_or_update(filename, actual)
