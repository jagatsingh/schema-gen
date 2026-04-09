"""Zod cross-file import + index re-export tests (POC findings C4, C5)."""

from __future__ import annotations

from schema_gen import Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry

# Module-level schemas so forward-reference resolution (which runs at
# decorator time) can see the referenced classes. Registry is cleared in
# each test to avoid cross-test leakage.


@Schema
class _ZodExecCtx:
    account: str
    balance: float


@Schema
class _ZodOrderReq:
    order_id: str
    context: _ZodExecCtx


@Schema
class _ZodFoo:
    id: int


@Schema
class _ZodBar:
    id: int


def _reregister(*classes):
    SchemaRegistry._schemas.clear()
    for cls in classes:
        SchemaRegistry.register(cls)


class TestZodCrossFileImports:
    """Fix #C4: referenced nested schemas must emit import lines."""

    def test_nested_schema_emits_import(self, tmp_path):
        _reregister(_ZodExecCtx, _ZodOrderReq)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        order_ts = (out_dir / "zod" / "_zodorderreq.ts").read_text()
        assert "import { _ZodExecCtxSchema } from './_zodexecctx';" in order_ts
        assert "import type { _ZodExecCtx } from './_zodexecctx';" in order_ts


class TestZodIndexExportType:
    """Fix #C5: index.ts must use ``export type`` for inferred types."""

    def test_index_uses_export_type_for_types(self, tmp_path):
        _reregister(_ZodFoo, _ZodBar)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["zod"],
        )
        SchemaGenerationEngine(config).generate_all()

        index = (out_dir / "zod" / "index.ts").read_text()

        # Values (runtime schemas) are re-exported as values...
        assert "export { _ZodFooSchema } from './_zodfoo';" in index
        assert "export { _ZodBarSchema } from './_zodbar';" in index
        # ...and the inferred types are re-exported via `export type`.
        assert "export type { _ZodFoo } from './_zodfoo';" in index
        assert "export type { _ZodBar } from './_zodbar';" in index
