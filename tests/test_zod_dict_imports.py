"""Zod dict value-type generation and unused-import tests (#67)."""

from __future__ import annotations

from typing import Any

from schema_gen import Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry


@Schema
class _DictNested:
    name: str
    value: int


@Schema
class _DictNestedParent:
    mapping: dict[str, _DictNested]


@Schema
class _DictStrParent:
    mapping: dict[str, str]


@Schema
class _DictAnyParent:
    mapping: dict[str, Any]


@Schema
class _DictOptionalNestedParent:
    mapping: dict[str, _DictNested] | None


@Schema
class _DictListNestedParent:
    mapping: dict[str, list[_DictNested]]


def _reregister(*classes):
    SchemaRegistry._schemas.clear()
    for cls in classes:
        SchemaRegistry.register(cls)


class TestZodDictValueTypes:
    """Fix #67: dict[str, T] must use T's Zod type, not z.any()."""

    def test_dict_nested_schema_generates_record_with_schema_ref(self, tmp_path):
        """dict[str, NestedSchema] -> z.record(NestedSchemaSchema) with import."""
        _reregister(_DictNested, _DictNestedParent)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        parent_ts = (out_dir / "zod" / "_dictnestedparent.ts").read_text()
        assert "z.record(_DictNestedSchema)" in parent_ts
        assert "import { _DictNestedSchema } from './_dictnested';" in parent_ts

    def test_dict_str_generates_record_with_string(self, tmp_path):
        """dict[str, str] -> z.record(z.string())."""
        _reregister(_DictStrParent)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        parent_ts = (out_dir / "zod" / "_dictstrparent.ts").read_text()
        assert "z.record(z.string())" in parent_ts

    def test_dict_any_generates_record_with_any_no_unused_imports(self, tmp_path):
        """dict[str, Any] -> z.record(z.any()) with no unused imports."""
        _reregister(_DictAnyParent)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        parent_ts = (out_dir / "zod" / "_dictanyparent.ts").read_text()
        assert "z.record(z.any())" in parent_ts
        # No cross-file imports should exist (only 'import { z } from "zod"').
        assert parent_ts.count("import ") == 1

    def test_optional_dict_nested_appends_optional(self, tmp_path):
        """Optional[dict[str, NestedSchema]] -> z.record(...).optional()."""
        _reregister(_DictNested, _DictOptionalNestedParent)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        parent_ts = (out_dir / "zod" / "_dictoptionalnestedparent.ts").read_text()
        assert "z.record(_DictNestedSchema).optional()" in parent_ts
        assert "import { _DictNestedSchema } from './_dictnested';" in parent_ts

    def test_dict_list_nested_generates_record_with_array(self, tmp_path):
        """dict[str, list[NestedSchema]] -> z.record(z.array(NestedSchemaSchema))."""
        _reregister(_DictNested, _DictListNestedParent)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        parent_ts = (out_dir / "zod" / "_dictlistnestedparent.ts").read_text()
        assert "z.record(z.array(_DictNestedSchema))" in parent_ts
        assert "import { _DictNestedSchema } from './_dictnested';" in parent_ts
