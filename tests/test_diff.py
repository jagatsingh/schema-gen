"""Tests for schema-gen diff — breaking change detection."""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from schema_gen.cli.main import main
from schema_gen.diff.comparator import compare_schemas
from schema_gen.diff.formatter import format_github, format_json, format_text
from schema_gen.diff.rules import RuleId, StrictnessLevel, Violation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _schema_file(defs: dict, ref: str | None = None) -> dict:
    """Build a minimal JSON Schema file dict with ``$defs``."""
    schema: dict = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": defs,
    }
    if ref:
        schema["$ref"] = ref
    return schema


def _type_def(
    properties: dict | None = None,
    required: list[str] | None = None,
    enum: list | None = None,
) -> dict:
    """Build a ``$defs`` entry."""
    d: dict = {"type": "object", "properties": properties or {}}
    if required:
        d["required"] = required
    if enum is not None:
        d["enum"] = enum
    return d


# ---------------------------------------------------------------------------
# Rule tests — WIRE level
# ---------------------------------------------------------------------------


class TestTypeNoDelete:
    def test_deleted_type_in_defs(self):
        old = {"user.json": _schema_file({"User": _type_def()})}
        new = {"user.json": _schema_file({})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert len(vs) == 1
        assert vs[0].rule_id == RuleId.TYPE_NO_DELETE
        assert vs[0].schema_name == "User"

    def test_deleted_file(self):
        old = {"user.json": _schema_file({"User": _type_def(), "Admin": _type_def()})}
        new = {}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert len(vs) == 2
        assert all(v.rule_id == RuleId.TYPE_NO_DELETE for v in vs)

    def test_new_type_is_safe(self):
        old = {"user.json": _schema_file({})}
        new = {"user.json": _schema_file({"User": _type_def()})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestFieldNoDelete:
    def test_removed_field(self):
        old_def = _type_def(
            properties={"name": {"type": "string"}, "age": {"type": "integer"}}
        )
        new_def = _type_def(properties={"name": {"type": "string"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert len(vs) == 1
        assert vs[0].rule_id == RuleId.FIELD_NO_DELETE
        assert vs[0].field_name == "age"

    def test_added_field_is_safe(self):
        old_def = _type_def(properties={"name": {"type": "string"}})
        new_def = _type_def(
            properties={"name": {"type": "string"}, "age": {"type": "integer"}}
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestFieldSameType:
    def test_type_changed(self):
        old_def = _type_def(properties={"age": {"type": "string"}})
        new_def = _type_def(properties={"age": {"type": "boolean"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)

    def test_same_type_is_safe(self):
        old_def = _type_def(properties={"age": {"type": "integer"}})
        new_def = _type_def(properties={"age": {"type": "integer"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestFieldTypeNarrowed:
    def test_number_to_integer_is_narrowing(self):
        old_def = _type_def(properties={"val": {"type": "number"}})
        new_def = _type_def(properties={"val": {"type": "integer"}})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_TYPE_NARROWED for v in vs)
        # Should NOT also fire FIELD_SAME_TYPE for width changes.
        assert not any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)

    def test_integer_to_number_is_widening_safe(self):
        old_def = _type_def(properties={"val": {"type": "integer"}})
        new_def = _type_def(properties={"val": {"type": "number"}})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestFieldRequiredAdded:
    def test_new_required_field(self):
        old_def = _type_def(properties={"name": {"type": "string"}}, required=["name"])
        new_def = _type_def(
            properties={"name": {"type": "string"}, "email": {"type": "string"}},
            required=["name", "email"],
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_REQUIRED_ADDED for v in vs)
        assert any(v.field_name == "email" for v in vs)

    def test_new_optional_field_is_safe(self):
        old_def = _type_def(properties={"name": {"type": "string"}}, required=["name"])
        new_def = _type_def(
            properties={"name": {"type": "string"}, "bio": {"type": "string"}},
            required=["name"],
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestEnumValueNoDelete:
    def test_removed_enum_variant(self):
        old_defs = {
            "Status": {"type": "string", "enum": ["active", "inactive", "banned"]}
        }
        new_defs = {"Status": {"type": "string", "enum": ["active", "inactive"]}}
        old = {"s.json": _schema_file(old_defs)}
        new = {"s.json": _schema_file(new_defs)}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert len(vs) == 1
        assert vs[0].rule_id == RuleId.ENUM_VALUE_NO_DELETE
        assert "banned" in vs[0].message

    def test_added_enum_variant_is_safe(self):
        old_defs = {"Status": {"type": "string", "enum": ["active", "inactive"]}}
        new_defs = {
            "Status": {"type": "string", "enum": ["active", "inactive", "banned"]}
        }
        old = {"s.json": _schema_file(old_defs)}
        new = {"s.json": _schema_file(new_defs)}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []

    def test_inline_enum_removed(self):
        old_def = _type_def(
            properties={"status": {"type": "string", "enum": ["a", "b", "c"]}}
        )
        new_def = _type_def(
            properties={"status": {"type": "string", "enum": ["a", "b"]}}
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.ENUM_VALUE_NO_DELETE for v in vs)

    def test_enum_replaced_with_plain_type(self):
        """Removing enum constraint entirely should flag all values as deleted."""
        old_defs = {"Status": {"type": "string", "enum": ["active", "inactive"]}}
        new_defs = {"Status": {"type": "string"}}
        old = {"s.json": _schema_file(old_defs)}
        new = {"s.json": _schema_file(new_defs)}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        enum_vs = [v for v in vs if v.rule_id == RuleId.ENUM_VALUE_NO_DELETE]
        assert len(enum_vs) == 2
        assert any("active" in v.message for v in enum_vs)
        assert any("inactive" in v.message for v in enum_vs)

    def test_inline_enum_replaced_with_plain_type(self):
        old_def = _type_def(
            properties={"status": {"type": "string", "enum": ["a", "b"]}}
        )
        new_def = _type_def(properties={"status": {"type": "string"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        enum_vs = [v for v in vs if v.rule_id == RuleId.ENUM_VALUE_NO_DELETE]
        assert len(enum_vs) == 2


# ---------------------------------------------------------------------------
# Rule tests — WIRE_JSON level
# ---------------------------------------------------------------------------


class TestFieldSameName:
    def test_rename_detected(self):
        old_def = _type_def(properties={"user_name": {"type": "string"}})
        new_def = _type_def(properties={"username": {"type": "string"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        same_name = [v for v in vs if v.rule_id == RuleId.FIELD_SAME_NAME]
        assert len(same_name) == 1
        assert "user_name" in same_name[0].message
        assert "username" in same_name[0].message

    def test_not_flagged_at_wire_level(self):
        old_def = _type_def(properties={"user_name": {"type": "string"}})
        new_def = _type_def(properties={"username": {"type": "string"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert not any(v.rule_id == RuleId.FIELD_SAME_NAME for v in vs)

    def test_ambiguous_rename_not_flagged(self):
        """Multiple removed+added string fields should not flag a rename."""
        old_def = _type_def(
            properties={
                "email": {"type": "string"},
                "phone": {"type": "string"},
            }
        )
        new_def = _type_def(
            properties={
                "contact_email": {"type": "string"},
                "mobile": {"type": "string"},
            }
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        same_name = [v for v in vs if v.rule_id == RuleId.FIELD_SAME_NAME]
        assert same_name == []


class TestEnumValueSameName:
    def test_value_changed_at_position(self):
        old_defs = {"Status": {"type": "string", "enum": ["active", "inactive"]}}
        new_defs = {"Status": {"type": "string", "enum": ["enabled", "inactive"]}}
        old = {"s.json": _schema_file(old_defs)}
        new = {"s.json": _schema_file(new_defs)}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        same_name = [v for v in vs if v.rule_id == RuleId.ENUM_VALUE_SAME_NAME]
        assert len(same_name) == 1
        assert "active" in same_name[0].message
        assert "enabled" in same_name[0].message

    def test_not_flagged_at_wire_level(self):
        old_defs = {"Status": {"type": "string", "enum": ["active", "inactive"]}}
        new_defs = {"Status": {"type": "string", "enum": ["enabled", "inactive"]}}
        old = {"s.json": _schema_file(old_defs)}
        new = {"s.json": _schema_file(new_defs)}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert not any(v.rule_id == RuleId.ENUM_VALUE_SAME_NAME for v in vs)


# ---------------------------------------------------------------------------
# Ignore flag
# ---------------------------------------------------------------------------


class TestIgnore:
    def test_ignore_suppresses_rule(self):
        old = {"u.json": _schema_file({"User": _type_def()})}
        new = {"u.json": _schema_file({})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE, ignore=["TYPE_NO_DELETE"])
        assert vs == []

    def test_ignore_only_specified_rule(self):
        old_def = _type_def(
            properties={"name": {"type": "string"}, "age": {"type": "integer"}},
            required=["name"],
        )
        new_def = _type_def(
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs_all = compare_schemas(old, new, StrictnessLevel.WIRE)
        vs_ignore = compare_schemas(
            old, new, StrictnessLevel.WIRE, ignore=["FIELD_NO_DELETE"]
        )
        assert len(vs_ignore) < len(vs_all)


# ---------------------------------------------------------------------------
# Safe changes
# ---------------------------------------------------------------------------


class TestRefAndAnyOfTypes:
    def test_ref_same_is_safe(self):
        old_def = _type_def(properties={"role": {"$ref": "#/$defs/Role"}})
        new_def = _type_def(properties={"role": {"$ref": "#/$defs/Role"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []

    def test_ref_changed(self):
        old_def = _type_def(properties={"role": {"$ref": "#/$defs/Role"}})
        new_def = _type_def(properties={"role": {"$ref": "#/$defs/Permission"}})
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)

    def test_anyof_same_is_safe(self):
        anyof = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        old_def = _type_def(properties={"val": anyof})
        new_def = _type_def(properties={"val": anyof})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []

    def test_anyof_reordered_is_safe(self):
        """Different ordering of anyOf variants should not be a type change."""
        old_anyof = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        new_anyof = {"anyOf": [{"type": "integer"}, {"type": "string"}]}
        old_def = _type_def(properties={"val": old_anyof})
        new_def = _type_def(properties={"val": new_anyof})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []

    def test_anyof_changed(self):
        old_anyof = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        new_anyof = {"anyOf": [{"type": "string"}, {"type": "boolean"}]}
        old_def = _type_def(properties={"val": old_anyof})
        new_def = _type_def(properties={"val": new_anyof})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)

    def test_list_type_ordering_is_safe(self):
        """JSON Schema list types like ["string", "null"] should match regardless of order."""
        old_def = _type_def(properties={"val": {"type": ["string", "null"]}})
        new_def = _type_def(properties={"val": {"type": ["null", "string"]}})
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []


class TestArrayItemsType:
    def test_array_item_type_change_detected(self):
        """Changing array<string> to array<integer> should be a type change."""
        old_def = _type_def(
            properties={"tags": {"type": "array", "items": {"type": "string"}}}
        )
        new_def = _type_def(
            properties={"tags": {"type": "array", "items": {"type": "integer"}}}
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)

    def test_array_same_item_type_is_safe(self):
        old_def = _type_def(
            properties={"tags": {"type": "array", "items": {"type": "string"}}}
        )
        new_def = _type_def(
            properties={"tags": {"type": "array", "items": {"type": "string"}}}
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert vs == []

    def test_array_ref_item_type_change(self):
        old_def = _type_def(
            properties={"legs": {"type": "array", "items": {"$ref": "#/$defs/Leg"}}}
        )
        new_def = _type_def(
            properties={"legs": {"type": "array", "items": {"$ref": "#/$defs/Step"}}}
        )
        old = {"u.json": _schema_file({"T": old_def})}
        new = {"u.json": _schema_file({"T": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE)
        assert any(v.rule_id == RuleId.FIELD_SAME_TYPE for v in vs)


class TestInlineEnumValueSameName:
    def test_inline_enum_value_changed(self):
        old_def = _type_def(
            properties={"status": {"type": "string", "enum": ["active", "inactive"]}}
        )
        new_def = _type_def(
            properties={"status": {"type": "string", "enum": ["enabled", "inactive"]}}
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        same_name = [v for v in vs if v.rule_id == RuleId.ENUM_VALUE_SAME_NAME]
        assert len(same_name) == 1
        assert same_name[0].field_name == "status"


class TestSafeChanges:
    def test_new_schema_file_is_safe(self):
        old: dict = {}
        new = {"user.json": _schema_file({"User": _type_def()})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        assert vs == []

    def test_add_optional_field_with_default_is_safe(self):
        old_def = _type_def(properties={"name": {"type": "string"}}, required=["name"])
        new_def = _type_def(
            properties={
                "name": {"type": "string"},
                "bio": {"type": "string", "default": ""},
            },
            required=["name"],
        )
        old = {"u.json": _schema_file({"User": old_def})}
        new = {"u.json": _schema_file({"User": new_def})}
        vs = compare_schemas(old, new, StrictnessLevel.WIRE_JSON)
        assert vs == []


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestFormatText:
    def test_empty(self):
        assert format_text([]) == ""

    def test_single_violation(self):
        v = Violation(
            rule_id=RuleId.FIELD_NO_DELETE,
            schema_name="User",
            field_name="age",
            message="Field 'age' was deleted from 'User'",
            level=StrictnessLevel.WIRE,
        )
        text = format_text([v])
        assert "1 breaking change" in text
        assert "FIELD_NO_DELETE" in text
        assert "User.age" in text


class TestFormatJson:
    def test_empty(self):
        result = json.loads(format_json([]))
        assert result == []

    def test_single_violation(self):
        v = Violation(
            rule_id=RuleId.FIELD_NO_DELETE,
            schema_name="User",
            field_name="age",
            message="Field 'age' was deleted from 'User'",
            level=StrictnessLevel.WIRE,
        )
        result = json.loads(format_json([v]))
        assert len(result) == 1
        assert result[0]["rule"] == "FIELD_NO_DELETE"
        assert result[0]["schema"] == "User"
        assert result[0]["field"] == "age"


class TestFormatGithub:
    def test_empty(self):
        assert format_github([]) == ""

    def test_single_violation(self):
        v = Violation(
            rule_id=RuleId.FIELD_NO_DELETE,
            schema_name="User",
            field_name="age",
            message="Field 'age' was deleted from 'User'",
            level=StrictnessLevel.WIRE,
        )
        output = format_github([v])
        assert output.startswith("::error ")
        assert "FIELD_NO_DELETE" in output
        assert "User.age" in output
        assert "Field 'age' was deleted from 'User'" in output

    def test_multiple_violations(self):
        vs = [
            Violation(
                rule_id=RuleId.FIELD_NO_DELETE,
                schema_name="User",
                field_name="age",
                message="deleted",
                level=StrictnessLevel.WIRE,
            ),
            Violation(
                rule_id=RuleId.TYPE_NO_DELETE,
                schema_name="Order",
                field_name=None,
                message="removed",
                level=StrictnessLevel.WIRE,
            ),
        ]
        output = format_github(vs)
        lines = output.strip().splitlines()
        assert len(lines) == 2
        assert all(line.startswith("::error ") for line in lines)


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestDiffCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_diff_help(self):
        result = self.runner.invoke(main, ["diff", "--help"])
        assert result.exit_code == 0
        assert "--against" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    @patch("schema_gen.cli.main.load_baseline")
    def test_diff_no_breaking_changes(self, mock_baseline, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        schema = _schema_file(
            {"User": _type_def(properties={"name": {"type": "string"}})}
        )
        mock_baseline.return_value = {"user.json": schema}
        mock_current.return_value = {"user.json": schema}

        result = self.runner.invoke(main, ["diff", "--against", ".git#branch=main"])
        assert result.exit_code == 0
        assert "No breaking changes" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    @patch("schema_gen.cli.main.load_baseline")
    def test_diff_with_breaking_changes(self, mock_baseline, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        old_schema = _schema_file(
            {"User": _type_def(properties={"name": {"type": "string"}})}
        )
        new_schema = _schema_file({"User": _type_def(properties={})})
        mock_baseline.return_value = {"user.json": old_schema}
        mock_current.return_value = {"user.json": new_schema}

        result = self.runner.invoke(main, ["diff", "--against", ".git#branch=main"])
        assert result.exit_code == 1
        assert "FIELD_NO_DELETE" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    @patch("schema_gen.cli.main.load_baseline")
    def test_diff_json_format(self, mock_baseline, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        old_schema = _schema_file(
            {"User": _type_def(properties={"name": {"type": "string"}})}
        )
        new_schema = _schema_file({"User": _type_def(properties={})})
        mock_baseline.return_value = {"user.json": old_schema}
        mock_current.return_value = {"user.json": new_schema}

        result = self.runner.invoke(
            main, ["diff", "--against", ".git#branch=main", "--format", "json"]
        )
        assert result.exit_code == 1
        parsed = json.loads(result.output)
        assert len(parsed) >= 1
        assert parsed[0]["rule"] == "FIELD_NO_DELETE"

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    @patch("schema_gen.cli.main.load_baseline")
    def test_diff_github_format(self, mock_baseline, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        old_schema = _schema_file(
            {"User": _type_def(properties={"name": {"type": "string"}})}
        )
        new_schema = _schema_file({"User": _type_def(properties={})})
        mock_baseline.return_value = {"user.json": old_schema}
        mock_current.return_value = {"user.json": new_schema}

        result = self.runner.invoke(
            main, ["diff", "--against", ".git#branch=main", "--format", "github"]
        )
        assert result.exit_code == 1
        assert "::error " in result.output
        assert "FIELD_NO_DELETE" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    @patch("schema_gen.cli.main.load_baseline")
    def test_diff_with_ignore(self, mock_baseline, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        old_schema = _schema_file(
            {"User": _type_def(properties={"name": {"type": "string"}})}
        )
        new_schema = _schema_file({"User": _type_def(properties={})})
        mock_baseline.return_value = {"user.json": old_schema}
        mock_current.return_value = {"user.json": new_schema}

        result = self.runner.invoke(
            main,
            ["diff", "--against", ".git#branch=main", "--ignore", "FIELD_NO_DELETE"],
        )
        assert result.exit_code == 0
        assert "No breaking changes" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    @patch("schema_gen.cli.main.load_current")
    def test_diff_baseline_error(self, mock_current, mock_engine):
        mock_engine.return_value.config.output_dir = "generated/"
        mock_current.return_value = {}

        result = self.runner.invoke(main, ["diff", "--against", "/nonexistent/path"])
        assert result.exit_code == 2

    def test_diff_invalid_ignore_rule(self):
        """Typo in --ignore should error with exit code 2."""
        result = self.runner.invoke(
            main,
            ["diff", "--against", ".git#branch=main", "--ignore", "FIELD_NO_DELET"],
        )
        assert result.exit_code == 2
        assert "Unknown rule" in result.output


# ---------------------------------------------------------------------------
# Baseline loader tests
# ---------------------------------------------------------------------------


class TestBaselineLoader:
    def test_parse_git_branch(self):
        from schema_gen.diff.baseline import _parse_git_ref

        assert _parse_git_ref(".git#branch=main") == "main"

    def test_parse_git_tag(self):
        from schema_gen.diff.baseline import _parse_git_ref

        assert _parse_git_ref(".git#tag=v1.0.0") == "v1.0.0"

    def test_parse_git_commit(self):
        from schema_gen.diff.baseline import _parse_git_ref

        assert _parse_git_ref(".git#commit=abc123") == "abc123"

    def test_parse_invalid_format(self):
        from schema_gen.diff.baseline import BaselineError, _parse_git_ref

        with pytest.raises(BaselineError):
            _parse_git_ref(".git#invalid")

    def test_load_from_directory(self, tmp_path):
        from schema_gen.diff.baseline import _load_from_directory

        schema = _schema_file({"User": _type_def()})
        (tmp_path / "user.json").write_text(json.dumps(schema))

        result = _load_from_directory(str(tmp_path))
        assert "user.json" in result
        assert result["user.json"]["$defs"]["User"]["type"] == "object"

    def test_load_from_nonexistent_directory(self):
        from schema_gen.diff.baseline import BaselineError, _load_from_directory

        with pytest.raises(BaselineError, match="not found"):
            _load_from_directory("/nonexistent/path")

    def test_load_current(self, tmp_path):
        from schema_gen.diff.baseline import load_current

        jsonschema_dir = tmp_path / "jsonschema"
        jsonschema_dir.mkdir()
        schema = _schema_file({"User": _type_def()})
        (jsonschema_dir / "user.json").write_text(json.dumps(schema))

        result = load_current(str(tmp_path))
        assert "user.json" in result

    def test_load_current_no_dir(self, tmp_path):
        from schema_gen.diff.baseline import BaselineError, load_current

        with pytest.raises(BaselineError, match="No jsonschema directory"):
            load_current(str(tmp_path))

    @patch("schema_gen.diff.baseline._git_show")
    @patch("schema_gen.diff.baseline._discover_baseline_json_files")
    def test_load_from_git(self, mock_baseline_files, mock_git_show, tmp_path):
        from schema_gen.diff.baseline import load_baseline

        # Set up current files so _discover_current_json_files works.
        jsonschema_dir = tmp_path / "jsonschema"
        jsonschema_dir.mkdir()
        (jsonschema_dir / "user.json").write_text("{}")

        mock_baseline_files.return_value = ["user.json"]
        schema = _schema_file({"User": _type_def()})
        mock_git_show.return_value = json.dumps(schema)

        result = load_baseline(".git#branch=main", str(tmp_path))
        assert "user.json" in result
        mock_git_show.assert_called_once()

    @patch("schema_gen.diff.baseline._git_show")
    @patch("schema_gen.diff.baseline._discover_baseline_json_files")
    def test_load_from_git_detects_deleted_files(
        self, mock_baseline_files, mock_git_show, tmp_path
    ):
        """Files that exist at the baseline but are deleted locally should still be loaded."""
        from schema_gen.diff.baseline import load_baseline

        # Only user.json exists locally; order.json was deleted.
        jsonschema_dir = tmp_path / "jsonschema"
        jsonschema_dir.mkdir()
        (jsonschema_dir / "user.json").write_text("{}")

        # Baseline ref has both files.
        mock_baseline_files.return_value = ["order.json", "user.json"]

        user_schema = _schema_file({"User": _type_def()})
        order_schema = _schema_file({"Order": _type_def()})

        def git_show_side_effect(ref, path):
            if "order.json" in path:
                return json.dumps(order_schema)
            if "user.json" in path:
                return json.dumps(user_schema)
            return None

        mock_git_show.side_effect = git_show_side_effect

        result = load_baseline(".git#branch=main", str(tmp_path))
        assert "user.json" in result
        assert "order.json" in result
