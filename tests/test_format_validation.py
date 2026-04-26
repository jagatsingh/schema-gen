"""Cross-format consistency tests.

Verifies invariants that span multiple generators — e.g. every generator
emits all schema fields, and "required vs optional" maps consistently
across formats. Per-generator syntactic and execution validation lives
elsewhere:

- ``test_generator_output_stability.py`` — golden snapshot tests
- ``test_generator_correctness_invariants.py`` — AST-level correctness
- ``test_generator_framework_execution.py`` — load + use in real frameworks

Historical note: this file used to also contain ``TestFormatValidation``
and ``TestGeneratedCodeExecution`` (~540 lines) that performed weak
substring checks and ran external compilers under
``contextlib.suppress(Exception)``. Both classes hid the protobuf and
SQLAlchemy bugs that surfaced in PR #102 review and were removed in
favor of the three test files above, which fail loudly.
"""

import json

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.dataclasses_generator import DataclassesGenerator
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pathway_generator import PathwayGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
from schema_gen.generators.typeddict_generator import TypedDictGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestCrossFormatConsistency:
    """Test that all formats generate consistent field mappings"""

    def setup_method(self):
        """Set up test schema"""
        SchemaRegistry._schemas.clear()

        @Schema
        class ConsistencyTest:
            """Schema for testing cross-format consistency"""

            required_int: int = Field(description="Required integer field")
            optional_str: str | None = Field(
                default=None, description="Optional string"
            )
            constrained_float: float = Field(min_value=0.0, max_value=100.0)
            boolean_field: bool = Field(default=False)

        parser = SchemaParser()
        self.schemas = parser.parse_all_schemas()
        self.test_schema = self.schemas[0]

    def test_field_presence_consistency(self):
        """Test that all generators include the same fields"""
        generators = {
            "pydantic": PydanticGenerator(),
            "sqlalchemy": SqlAlchemyGenerator(),
            "dataclasses": DataclassesGenerator(),
            "typeddict": TypedDictGenerator(),
            "pathway": PathwayGenerator(),
        }

        field_names = {field.name for field in self.test_schema.fields}

        for generator_name, generator in generators.items():
            generated_code = generator.generate_file(self.test_schema)

            # Check that all field names appear in generated code
            for field_name in field_names:
                assert field_name in generated_code, (
                    f"Field '{field_name}' missing from {generator_name} output"
                )

    def test_required_fields_consistency(self):
        """Test that required fields are consistently marked across formats"""
        json_generator = JsonSchemaGenerator()
        schema_json = json_generator.generate_model(self.test_schema)
        schema = json.loads(schema_json)

        # Required fields should include fields without defaults
        required_fields = schema.get("required", [])

        # required_int should be required (no default)
        assert "required_int" in required_fields

        # optional_str should not be required (has default=None)
        assert "optional_str" not in required_fields

        # boolean_field should not be required (has default=False)
        assert "boolean_field" not in required_fields
