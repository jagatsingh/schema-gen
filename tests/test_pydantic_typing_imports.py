"""Regression tests for issue #99: pydantic generator emits unused typing imports.

The pydantic generator historically emitted ``from typing import Any, Optional,
Union`` whenever any typing name was referenced, even if the file used only
``Optional``. This caused F401 warnings on downstream consumers' CI.

These tests guard two invariants:

1. **Minimal imports** — generated files only import the typing names they
   actually use. ``Optional``-only schemas don't pull ``Any`` or ``Union``.
2. **No collateral churn** — schemas that legitimately need all three names
   (the historical "everything" case) still emit ``Any, Optional, Union``
   unchanged, so downstream regenerations produce a diff only on the typing
   import line, never on class bodies.
"""

from __future__ import annotations

from enum import Enum

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class _TradeMode(str, Enum):
    """Operating mode for the matching engine.

    ``LIVE`` connects to the exchange. ``REPLAY`` reads from a
    historical capture and produces synthetic fills.
    """

    LIVE = "live"
    REPLAY = "replay"


def _generate(cls) -> str:
    SchemaRegistry._schemas.clear()
    schema = SchemaParser().parse_schema(cls)
    return PydanticGenerator().generate_file(schema)


class TestTypingImportsMinimal:
    """Issue #99: only the typing names actually used should be imported."""

    def test_optional_only_does_not_import_any_or_union(self):
        @Schema
        class OptionalOnly:
            name: str = Field(...)
            nickname: str | None = Field(default=None)

        out = _generate(OptionalOnly)
        assert "from typing import Optional" in out
        # The exact typing line — no Any/Union polluting it.
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        assert typing_line == "from typing import Optional", typing_line

    def test_any_only_does_not_import_optional_or_union(self):
        @Schema
        class AnyOnly:
            meta: dict = Field(default_factory=dict)

        out = _generate(AnyOnly)
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        assert typing_line == "from typing import Any", typing_line

    def test_union_only_does_not_import_optional_or_any(self):
        @Schema
        class UnionOnly:
            value: int | str = Field(...)

        out = _generate(UnionOnly)
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        assert typing_line == "from typing import Union", typing_line

    def test_no_typing_at_all_emits_no_typing_import(self):
        @Schema
        class NoTyping:
            name: str = Field(...)
            count: int = Field(...)

        out = _generate(NoTyping)
        assert "from typing" not in out

    def test_optional_plus_any_imports_both_only(self):
        @Schema
        class OptAndAny:
            nickname: str | None = Field(default=None)
            meta: dict = Field(default_factory=dict)

        out = _generate(OptAndAny)
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        # Imports are sorted alphabetically.
        assert typing_line == "from typing import Any, Optional", typing_line


class TestNoCollateralChurnForExistingConsumers:
    """Schemas that need all three names must produce identical output to v0.3.8.

    This guards downstream regenerations (tradingcore, tradingutils,
    trading-platform): the diff after bumping schema-gen must be limited to
    the typing import line — class bodies, field order, and field definitions
    must be byte-identical.
    """

    def test_all_three_names_still_imported_together(self):
        @Schema
        class NeedsAll:
            nickname: str | None = Field(default=None)
            meta: dict = Field(default_factory=dict)
            value: int | str = Field(...)

        out = _generate(NeedsAll)
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        assert typing_line == "from typing import Any, Optional, Union", typing_line

    def test_class_body_unchanged_for_optional_only_schema(self):
        """The non-import portion of the file must be unchanged from v0.3.8."""

        @Schema
        class OptionalOnly:
            name: str = Field(...)
            nickname: str | None = Field(default=None)

        out = _generate(OptionalOnly)
        # The class definition and its fields are unchanged.
        assert "class OptionalOnly(BaseModel):" in out
        assert "    name: str = Field(default=Ellipsis)" in out
        assert "    nickname: Optional[str] = Field(default=None)" in out


class TestMultiLineClassDocstring:
    """Regression for tradingcore PR #400 Copilot review.

    Multi-line BaseModel class docstrings must follow PEP 257: the summary
    on the opening triple-quote line, body lines indented to match the
    class body, and the closing triple-quote on its own line. The previous
    output collapsed the closing ``\"\"\"`` onto the last sentence and lost
    body-line indentation.
    """

    def test_multi_line_docstring_pep257_form(self):
        @Schema
        class WithMultiLine:
            """Payload pushed by the suggestion runner when regime changes affect open trades.

            Sent to POST /suggestions/trades/adjust. Applies the adjustment
            to all open/accepted trades matching the instrument and strategy.
            """

            instrument: str = Field(...)

        out = _generate(WithMultiLine)
        # Anchor all assertions to the class block so the file-header
        # docstring (which also opens with ``"""\n``) cannot satisfy them
        # by accident.
        class_block = out.split("class WithMultiLine(BaseModel):", 1)[1]
        # Summary attaches to opening triple-quote.
        assert (
            '    """Payload pushed by the suggestion runner when regime changes affect open trades.'
            in class_block
        )
        # Body lines are indented to match the class body (4 spaces).
        assert "    Sent to POST /suggestions/trades/adjust." in class_block
        assert "\nSent to POST" not in class_block, "body lines must not be unindented"
        # Closing triple-quote on its own line, not glued to last sentence.
        assert 'instrument and strategy."""' not in class_block
        assert '    """\n' in class_block, (
            "closing triple-quote must be on its own line"
        )

    def test_single_line_docstring_unchanged(self):
        """Single-line docstrings stay in the compact ``\"\"\"...\"\"\"`` form."""

        @Schema
        class Flat:
            """Just one line."""

            instrument: str = Field(...)

        out = _generate(Flat)
        assert '    """Just one line."""' in out

    def test_no_docstring_emits_no_docstring_block(self):
        @Schema
        class NoDoc:
            instrument: str = Field(...)

        out = _generate(NoDoc)
        assert (
            '"""' not in out.split("class NoDoc(BaseModel):")[1].split("instrument:")[0]
        ), "no docstring block should be emitted between class header and first field"

    def test_multi_line_docstring_via_generate_model(self):
        """The Jinja template path must also emit PEP 257 multi-line form."""
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        SchemaRegistry._schemas.clear()

        @Schema
        class WithMultiLine:
            """Summary line for model.

            Body line one.
            Body line two.
            """

            instrument: str = Field(...)

        schema = SchemaParser().parse_schema(WithMultiLine)
        out = PydanticGenerator().generate_model(schema)
        # Anchor to the class block so the file-header docstring cannot
        # mask a regression.
        class_block = out.split("class WithMultiLine(BaseModel):", 1)[1]
        assert '    """Summary line for model.' in class_block
        assert "    Body line one." in class_block
        assert "    Body line two." in class_block
        # Closing triple-quote on its own line.
        assert 'Body line two."""' not in class_block

    def test_multi_line_enum_docstring_pep257_form(self):
        """Enums share ``_format_class_docstring``; multi-line enum docstrings
        must also follow PEP 257 in the generated ``_enums.py``."""
        from pathlib import Path

        from schema_gen.generators.pydantic_generator import PydanticGenerator

        SchemaRegistry._schemas.clear()

        @Schema
        class HasMode:
            mode: _TradeMode = Field(default=_TradeMode.LIVE)

        schemas = [SchemaParser().parse_schema(HasMode)]
        extras = PydanticGenerator().get_extra_files(schemas, Path("/tmp"))
        enums_py = extras["_enums.py"]
        # Anchor to the enum class block.
        class_block = enums_py.split("class _TradeMode(str, Enum):", 1)[1]
        assert '    """Operating mode for the matching engine.' in class_block
        assert "    ``LIVE`` connects to the exchange." in class_block
        # Closing triple-quote on its own line, not on the last sentence.
        assert 'synthetic fills."""' not in class_block
        assert '    """\n' in class_block


class TestTypingImportsViaGenerateModel:
    """Issue #99 invariant must also hold via the Jinja template path
    (``generate_model``), not only ``generate_file``."""

    def test_optional_only_via_generate_model(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        SchemaRegistry._schemas.clear()

        @Schema
        class OptionalOnly:
            nickname: str | None = Field(default=None)

        schema = SchemaParser().parse_schema(OptionalOnly)
        out = PydanticGenerator().generate_model(schema)
        typing_line = next(
            line for line in out.splitlines() if line.startswith("from typing import")
        )
        assert typing_line == "from typing import Optional", typing_line

    def test_no_typing_via_generate_model(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        SchemaRegistry._schemas.clear()

        @Schema
        class NoTyping:
            name: str = Field(...)
            count: int = Field(...)

        schema = SchemaParser().parse_schema(NoTyping)
        out = PydanticGenerator().generate_model(schema)
        assert "from typing" not in out
