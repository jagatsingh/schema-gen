"""Test that Zod generator emits trailing commas in z.object() fields."""

from __future__ import annotations

from schema_gen import Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


@Schema
class _ZodCommaOrder:
    request_id: str
    signal_id: str
    quantity: int


class TestZodObjectCommas:
    def setup_method(self):
        SchemaRegistry._schemas.clear()
        SchemaRegistry.register(_ZodCommaOrder)

    def test_zod_object_fields_have_commas(self):
        """Each field in z.object() must end with a comma."""
        schema = SchemaParser().parse_schema(_ZodCommaOrder)
        out = ZodGenerator().generate_file(schema)
        assert "z.string()," in out
        assert "z.number().int()," in out
