"""Tests for USR validation logic"""

from schema_gen.core.usr import (
    FieldType,
    USRField,
    USRSchema,
    ValidationIssue,
)


def _make_field(name: str = "test_field", **kwargs) -> USRField:
    """Helper to create a USRField with sensible defaults."""
    defaults = {
        "type": FieldType.STRING,
        "python_type": str,
    }
    defaults.update(kwargs)
    return USRField(name=name, **defaults)


class TestValidationIssueDataclass:
    """Ensure ValidationIssue is a proper dataclass."""

    def test_creation(self):
        issue = ValidationIssue(severity="error", field_name="id", message="bad")
        assert issue.severity == "error"
        assert issue.field_name == "id"
        assert issue.message == "bad"

    def test_field_name_can_be_none(self):
        issue = ValidationIssue(severity="info", field_name=None, message="ok")
        assert issue.field_name is None


class TestUSRFieldValidation:
    """Tests for USRField.validate()"""

    def test_valid_field_no_issues(self):
        f = _make_field()
        assert f.validate() == []

    def test_primary_key_and_optional_warns(self):
        f = _make_field(primary_key=True, optional=True)
        issues = f.validate()
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "primary_key" in issues[0].message
        assert "optional" in issues[0].message

    def test_primary_key_not_optional_ok(self):
        f = _make_field(
            primary_key=True, optional=False, type=FieldType.INTEGER, python_type=int
        )
        assert f.validate() == []

    def test_list_without_inner_type_warns(self):
        f = _make_field(type=FieldType.LIST, python_type=list, inner_type=None)
        issues = f.validate()
        assert any(
            i.severity == "warning" and "inner_type" in i.message for i in issues
        )

    def test_list_with_inner_type_ok(self):
        inner = _make_field(name="item", type=FieldType.STRING)
        f = _make_field(type=FieldType.LIST, python_type=list, inner_type=inner)
        # Should not contain the inner_type warning
        issues = f.validate()
        assert not any("inner_type" in i.message for i in issues)

    def test_min_value_on_string_warns(self):
        f = _make_field(type=FieldType.STRING, min_value=0)
        issues = f.validate()
        assert any(i.severity == "warning" and "min_value" in i.message for i in issues)

    def test_max_value_on_boolean_warns(self):
        f = _make_field(type=FieldType.BOOLEAN, python_type=bool, max_value=1)
        issues = f.validate()
        assert any(
            i.severity == "warning"
            and "min_value" in i.message
            or "max_value" in i.message
            for i in issues
        )

    def test_min_value_on_integer_ok(self):
        f = _make_field(
            type=FieldType.INTEGER, python_type=int, min_value=0, max_value=100
        )
        assert f.validate() == []

    def test_min_value_on_float_ok(self):
        f = _make_field(type=FieldType.FLOAT, python_type=float, min_value=0.0)
        assert f.validate() == []

    def test_min_value_on_decimal_ok(self):
        import decimal

        f = _make_field(
            type=FieldType.DECIMAL, python_type=decimal.Decimal, min_value=0
        )
        assert f.validate() == []

    def test_min_length_on_integer_warns(self):
        f = _make_field(type=FieldType.INTEGER, python_type=int, min_length=1)
        issues = f.validate()
        assert any(
            i.severity == "warning" and "min_length" in i.message for i in issues
        )

    def test_max_length_on_string_ok(self):
        f = _make_field(type=FieldType.STRING, max_length=255)
        assert f.validate() == []

    def test_min_length_on_list_ok(self):
        inner = _make_field(name="item")
        f = _make_field(
            type=FieldType.LIST, python_type=list, inner_type=inner, min_length=1
        )
        assert f.validate() == []

    def test_enum_name_without_values_errors(self):
        f = _make_field(type=FieldType.ENUM, enum_name="Status", enum_values=[])
        issues = f.validate()
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "enum_name" in issues[0].message
        assert "enum_values" in issues[0].message

    def test_enum_name_with_values_ok(self):
        f = _make_field(
            type=FieldType.ENUM, enum_name="Status", enum_values=["active", "inactive"]
        )
        assert f.validate() == []

    def test_foreign_key_without_relationship_info(self):
        f = _make_field(
            type=FieldType.INTEGER,
            python_type=int,
            foreign_key="users.id",
            relationship=None,
        )
        issues = f.validate()
        assert any(i.severity == "info" and "foreign_key" in i.message for i in issues)

    def test_foreign_key_with_relationship_ok(self):
        f = _make_field(
            type=FieldType.INTEGER,
            python_type=int,
            foreign_key="users.id",
            relationship="many_to_one",
        )
        assert f.validate() == []

    def test_multiple_issues_on_one_field(self):
        """A single field can have several problems at once."""
        f = _make_field(
            type=FieldType.STRING,
            primary_key=True,
            optional=True,
            min_value=0,
            enum_name="Broken",
            enum_values=[],
        )
        issues = f.validate()
        severities = {i.severity for i in issues}
        assert "warning" in severities
        assert "error" in severities
        assert (
            len(issues) >= 3
        )  # pk+optional, min_value on string, enum_name w/o values


class TestUSRSchemaValidation:
    """Tests for USRSchema.validate()"""

    def test_valid_schema_no_issues(self):
        schema = USRSchema(
            name="User",
            fields=[
                _make_field(
                    "id", type=FieldType.INTEGER, python_type=int, primary_key=True
                ),
                _make_field("name", type=FieldType.STRING, max_length=100),
            ],
        )
        assert schema.validate() == []

    def test_schema_propagates_field_issues(self):
        schema = USRSchema(
            name="User",
            fields=[
                _make_field(
                    "id",
                    type=FieldType.INTEGER,
                    python_type=int,
                    primary_key=True,
                    optional=True,
                ),
            ],
        )
        issues = schema.validate()
        assert len(issues) == 1
        assert issues[0].field_name == "id"

    def test_variant_references_nonexistent_field_errors(self):
        schema = USRSchema(
            name="User",
            fields=[
                _make_field("id", type=FieldType.INTEGER, python_type=int),
                _make_field("name", type=FieldType.STRING),
            ],
            variants={"create": ["id", "name", "ghost_field"]},
        )
        issues = schema.validate()
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "ghost_field" in issues[0].message
        assert "create" in issues[0].message

    def test_variant_with_valid_fields_ok(self):
        schema = USRSchema(
            name="User",
            fields=[
                _make_field("id", type=FieldType.INTEGER, python_type=int),
                _make_field("name", type=FieldType.STRING),
            ],
            variants={"create": ["id", "name"]},
        )
        assert schema.validate() == []

    def test_multiple_variant_errors(self):
        schema = USRSchema(
            name="User",
            fields=[_make_field("id", type=FieldType.INTEGER, python_type=int)],
            variants={
                "create": ["id", "missing_a"],
                "update": ["missing_b"],
            },
        )
        issues = schema.validate()
        error_messages = [i.message for i in issues if i.severity == "error"]
        assert any("missing_a" in m for m in error_messages)
        assert any("missing_b" in m for m in error_messages)

    def test_combined_field_and_schema_issues(self):
        """Both field-level and schema-level issues are collected."""
        schema = USRSchema(
            name="Bad",
            fields=[
                _make_field("pk", primary_key=True, optional=True),
            ],
            variants={"v1": ["pk", "nope"]},
        )
        issues = schema.validate()
        assert len(issues) == 2
        severities = [i.severity for i in issues]
        assert "warning" in severities  # pk + optional
        assert "error" in severities  # variant ref
