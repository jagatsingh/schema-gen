"""Correctness invariants for generator output that snapshot tests can't catch.

Snapshot tests lock the *shape* of output but happily snapshot a buggy shape.
These tests assert *semantic* invariants that catch original-correctness bugs:

- The Protobuf generator emits valid syntax — every line outside a message
  block is either a directive, a comment, or a blank line.
- The SQLAlchemy generator emits the class docstring as the FIRST statement
  in the class body so ``ClassName.__doc__`` resolves to the description
  (Python's docstring rule, PEP 257).

These regressed in jagatsingh/schema-gen PR #102 review (Copilot caught
both); the snapshot tests in ``test_generator_output_stability.py`` did not
catch them because they were already buggy when the snapshots were taken.
"""

from __future__ import annotations

import ast

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.protobuf_generator import ProtobufGenerator
from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
from schema_gen.parsers.schema_parser import SchemaParser


@Schema
class _MultiLineDescSchema:
    """Summary line of the schema.

    Body line one, with extra detail.
    Body line two.
    """

    name: str = Field(description="x")
    count: int = Field(description="y")


def _parse():
    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(_MultiLineDescSchema)
    return SchemaParser().parse_schema(_MultiLineDescSchema)


class TestProtobufSyntaxValidity:
    """Multi-line schema descriptions must be properly commented in .proto output.

    Regression: prior to fix, only the first line of a multi-line description
    was prefixed with ``// ``; subsequent lines fell outside the comment
    block, producing invalid Protobuf syntax that ``protoc`` would reject.
    """

    def test_no_uncommented_text_outside_message_blocks(self):
        out = ProtobufGenerator().generate_file(_parse())
        # A simple syntactic check: outside ``message ... { ... }`` and
        # service/RPC blocks, every non-blank line must start with ``//``,
        # ``syntax``, ``package``, or ``import``.
        in_block = 0
        valid_directive_starts = ("syntax ", "package ", "import ")
        for lineno, line in enumerate(out.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if "{" in stripped:
                in_block += stripped.count("{")
            if "}" in stripped:
                in_block -= stripped.count("}")
                continue
            if in_block > 0:
                continue
            assert stripped.startswith("//") or stripped.startswith(
                valid_directive_starts
            ), (
                f"Line {lineno} is outside any message/service block but is "
                f"neither a comment nor a Protobuf directive: {line!r}"
            )

    def test_multi_line_description_lines_are_each_commented(self):
        out = ProtobufGenerator().generate_file(_parse())
        # All four source-doc lines must appear as ``// `` prefixed comments.
        assert "// Summary line of the schema." in out
        assert "// Body line one, with extra detail." in out
        assert "// Body line two." in out
        # Empty separator line preserves paragraph break as bare ``//``.
        assert "\n//\n" in out


class TestSqlalchemyDocstringIsFirstClassStatement:
    """The SQLAlchemy class docstring must be recognized by Python.

    Regression: prior to fix, the docstring was emitted *after*
    ``__tablename__``, making it a no-op string expression and leaving
    ``ClassName.__doc__`` as ``None``. PEP 257 requires the docstring to
    be the first statement in the class body.
    """

    def test_docstring_is_first_statement_in_class_body(self):
        # ``ast.parse`` also serves as a syntax-check; a malformed file
        # raises ``SyntaxError`` here before we reach the docstring assert.
        out = SqlAlchemyGenerator().generate_file(_parse())
        tree = ast.parse(out)
        cls = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "_MultiLineDescSchema"
        )
        docstring = ast.get_docstring(cls)
        assert docstring is not None, (
            "SQLAlchemy class has no recognized docstring — it was likely "
            "emitted after __tablename__ instead of as the first body statement"
        )
        assert "Summary line of the schema." in docstring
        assert "Body line one, with extra detail." in docstring
