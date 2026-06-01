"""Tests for top-level / standalone discriminated unions (#131).

``register_union(name, Annotated[Union[...], Field(discriminator=...)])``
declares a discriminated union that is a wire type in its own right — not a
field on a ``@Schema`` — so the generators emit a real tagged union named
``name`` (Rust internally-tagged enum, Zod ``z.discriminatedUnion``, Pydantic
``Annotated[Union, Field(discriminator=...)]``, JSON Schema ``oneOf`` +
discriminator) instead of nothing.

Generators that can't express a tagged union opt out via
``supports_root_union = False`` and the engine skips the union for them
rather than emitting a misleading struct.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Literal

import pytest

from schema_gen import Field, Schema, register_union
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

# -----------------------------------------------------------------------
# Fixtures — module-level for forward-reference resolution
# -----------------------------------------------------------------------


@Schema
class SUFuturesMarketOrder:
    """Market order — discriminator value "market"."""

    order_type: Literal["market"]
    qty: int


@Schema
class SUFuturesLimitOrder:
    """Limit order — discriminator value "limit"."""

    order_type: Literal["limit"]
    qty: int
    limit_price: float


# The standalone union alias under test.
SUFuturesOrderRequest = Annotated[
    SUFuturesMarketOrder | SUFuturesLimitOrder,
    Field(discriminator="order_type"),
]

WIRE_PAYLOADS = [
    {"order_type": "market", "qty": 1},
    {"order_type": "limit", "qty": 2, "limit_price": 3.5},
]


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _register_fixtures() -> None:
    """(Re-)register the fixture schemas + union into the global registry."""
    SchemaRegistry._schemas.clear()
    SchemaRegistry._unions.clear()
    SchemaRegistry.register(SUFuturesMarketOrder)
    SchemaRegistry.register(SUFuturesLimitOrder)
    register_union("SUFuturesOrderRequest", SUFuturesOrderRequest)


# -----------------------------------------------------------------------
# Parser / foundation
# -----------------------------------------------------------------------


class TestRootUnionParsing:
    def setup_method(self):
        _register_fixtures()

    def test_parse_all_includes_root_union(self):
        schemas = {s.name: s for s in SchemaParser().parse_all_schemas()}
        assert "SUFuturesOrderRequest" in schemas
        ru = schemas["SUFuturesOrderRequest"]
        assert ru.is_root_union is True
        f = ru.root_union_field
        assert f is not None
        assert f.discriminator == "order_type"
        assert [v.nested_schema for v in f.union_types] == [
            "SUFuturesMarketOrder",
            "SUFuturesLimitOrder",
        ]
        assert f.union_tag_values == ["market", "limit"]

    def test_variant_tag_fields_marked_skip(self):
        # The variant structs' discriminator field must be flagged so serde
        # emits #[serde(skip)] (the enum owns the tag on the wire).
        schemas = {s.name: s for s in SchemaParser().parse_all_schemas()}
        for variant in ("SUFuturesMarketOrder", "SUFuturesLimitOrder"):
            tag_field = schemas[variant].get_field("order_type")
            assert tag_field is not None
            assert tag_field.is_discriminator_tag is True

    def test_non_union_rejected(self):
        SchemaRegistry._schemas.clear()
        SchemaRegistry._unions.clear()
        SchemaRegistry.register(SUFuturesMarketOrder)
        register_union("Bad", SUFuturesMarketOrder)  # not a Union
        with pytest.raises(ValueError, match="non-union type"):
            SchemaParser().parse_all_schemas()

    def test_union_without_discriminator_rejected(self):
        SchemaRegistry._schemas.clear()
        SchemaRegistry._unions.clear()
        SchemaRegistry.register(SUFuturesMarketOrder)
        SchemaRegistry.register(SUFuturesLimitOrder)
        register_union(
            "Bad", SUFuturesMarketOrder | SUFuturesLimitOrder
        )  # no Field(discriminator=...)
        with pytest.raises(ValueError, match="discriminator"):
            SchemaParser().parse_all_schemas()

    def test_union_name_colliding_with_schema_rejected(self):
        SchemaRegistry._schemas.clear()
        SchemaRegistry._unions.clear()
        SchemaRegistry.register(SUFuturesMarketOrder)
        with pytest.raises(ValueError, match="already registered as a @Schema"):
            register_union("SUFuturesMarketOrder", SUFuturesOrderRequest)


# -----------------------------------------------------------------------
# First-class generator string assertions
# -----------------------------------------------------------------------


class TestRootUnionEmit:
    def setup_method(self):
        _register_fixtures()
        self.schemas = {s.name: s for s in SchemaParser().parse_all_schemas()}

    def _ru(self):
        return self.schemas["SUFuturesOrderRequest"]

    def test_rust_internally_tagged_enum(self):
        out = RustGenerator().generate_file(self._ru())
        assert '#[serde(tag = "order_type")]' in out
        assert "pub enum SUFuturesOrderRequest {" in out
        assert "Market(SUFuturesMarketOrder)," in out
        assert "Limit(SUFuturesLimitOrder)," in out
        # No struct emission for the union itself.
        assert "pub struct SUFuturesOrderRequest" not in out

    def test_zod_discriminated_union(self):
        out = ZodGenerator().generate_file(self._ru())
        assert (
            "export const SUFuturesOrderRequestSchema = "
            'z.discriminatedUnion("order_type", '
            "[SUFuturesMarketOrderSchema, SUFuturesLimitOrderSchema]);" in out
        )
        assert "z.union([" not in out
        assert (
            "import { SUFuturesMarketOrderSchema } from './sufuturesmarketorder';"
            in out
        )

    def test_jsonschema_oneof_plus_discriminator(self):
        doc = json.loads(JsonSchemaGenerator().generate_file(self._ru()))
        assert doc["title"] == "SUFuturesOrderRequest"
        assert doc["discriminator"] == {"propertyName": "order_type"}
        refs = {item["$ref"] for item in doc["oneOf"]}
        assert refs == {
            "sufuturesmarketorder.json#/$defs/SUFuturesMarketOrder",
            "sufutureslimitorder.json#/$defs/SUFuturesLimitOrder",
        }
        assert "$defs" not in doc  # standalone union is not a struct collection

    def test_pydantic_alias(self):
        out = PydanticGenerator().generate_file(self._ru())
        assert "from .sufuturesmarketorder_models import SUFuturesMarketOrder" in out
        assert "from .sufutureslimitorder_models import SUFuturesLimitOrder" in out
        assert "SUFuturesOrderRequest = Annotated[" in out
        assert 'Field(discriminator="order_type")' in out
        assert "class SUFuturesOrderRequest" not in out  # alias, not a model


# -----------------------------------------------------------------------
# Engine: non-supporting targets skip the union (no misleading struct)
# -----------------------------------------------------------------------


class TestEngineSkipsUnsupportedTargets:
    def setup_method(self):
        _register_fixtures()

    def test_dataclasses_target_skips_union(self, tmp_path: Path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cfg = Config(
            input_dir=str(out_dir / "in"),
            output_dir=str(out_dir),
            targets=["dataclasses"],
        )
        SchemaGenerationEngine(cfg).generate_all()
        files = {p.name for p in (out_dir / "dataclasses").glob("*.py")}
        # Variant structs emit; the union does NOT (no self-named-field class).
        assert "sufuturesmarketorder_models.py" in files
        assert "sufuturesorderrequest_models.py" not in files

    def test_rust_target_emits_union(self, tmp_path: Path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cfg = Config(
            input_dir=str(out_dir / "in"),
            output_dir=str(out_dir),
            targets=["rust"],
        )
        SchemaGenerationEngine(cfg).generate_all()
        files = {p.name for p in (out_dir / "rust").glob("*.rs")}
        assert "su_futures_order_request.rs" in files


# -----------------------------------------------------------------------
# Pydantic round-trip (always runs) — the alias validates via TypeAdapter
# -----------------------------------------------------------------------


class TestPydanticRoundTrip:
    def setup_method(self):
        _register_fixtures()

    def teardown_method(self):
        prefix = getattr(self, "_pkg_prefix", None)
        if prefix:
            for key in [k for k in sys.modules if k.startswith(prefix)]:
                sys.modules.pop(key, None)

    def _load_union(self, tmp_path: Path):
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cfg = Config(
            input_dir=str(out_dir / "in"),
            output_dir=str(out_dir),
            targets=["pydantic"],
        )
        SchemaGenerationEngine(cfg).generate_all()
        pydantic_dir = out_dir / "pydantic"
        pkg_name = "_su_pydantic_pkg"
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name,
            pydantic_dir / "__init__.py",
            submodule_search_locations=[str(pydantic_dir)],
        )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg_mod
        self._pkg_prefix = pkg_name
        pkg_spec.loader.exec_module(pkg_mod)
        return pkg_mod.SUFuturesOrderRequest

    @pytest.mark.parametrize("wire", WIRE_PAYLOADS)
    def test_pydantic_typeadapter_roundtrip(self, tmp_path: Path, wire: dict):
        from pydantic import TypeAdapter

        union_alias = self._load_union(tmp_path)
        adapter = TypeAdapter(union_alias)
        obj = adapter.validate_python(wire)
        emitted = json.loads(adapter.dump_json(obj))
        assert _canonical(emitted) == _canonical(wire)


# -----------------------------------------------------------------------
# Rust round-trip — compile a tiny harness, deserialize + re-serialize
# -----------------------------------------------------------------------

_RUST_MAIN = r"""
use generated::SUFuturesOrderRequest;
use std::io::Read;

fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    for line in input.lines().filter(|l| !l.trim().is_empty()) {
        let parsed: SUFuturesOrderRequest = serde_json::from_str(line).unwrap();
        let out = serde_json::to_string(&parsed).unwrap();
        println!("{}", out);
    }
}
"""


@pytest.mark.skipif(not shutil.which("cargo"), reason="cargo not installed")
def test_rust_roundtrip(tmp_path: Path):
    _register_fixtures()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    cfg = Config(
        input_dir=str(out_dir / "in"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    SchemaGenerationEngine(cfg).generate_all()
    rust_dir = out_dir / "rust"

    crate = tmp_path / "rt_crate"
    src = crate / "src"
    src.mkdir(parents=True)
    for rs in rust_dir.glob("*.rs"):
        shutil.copy(rs, src / rs.name)
    (src / "main.rs").write_text(_RUST_MAIN)

    (crate / "Cargo.toml").write_text(
        "[package]\n"
        'name = "generated"\n'
        'version = "0.0.0"\n'
        'edition = "2021"\n\n'
        "[dependencies]\n"
        'serde = { version = "1", features = ["derive"] }\n'
        'serde_json = "1"\n'
        'schemars = "0.8"\n\n'
        "[[bin]]\n"
        'name = "rt"\n'
        'path = "src/main.rs"\n'
    )

    payload = "\n".join(json.dumps(p) for p in WIRE_PAYLOADS)
    result = subprocess.run(
        ["cargo", "run", "--quiet", "--bin", "rt"],
        cwd=crate,
        input=payload,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"cargo run failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(lines) == len(WIRE_PAYLOADS)
    for emitted_line, wire in zip(lines, WIRE_PAYLOADS, strict=True):
        assert _canonical(json.loads(emitted_line)) == _canonical(wire)


# -----------------------------------------------------------------------
# Zod round-trip — parse + re-serialize via a compiled-then-run TS harness
# -----------------------------------------------------------------------

_ZOD_HARNESS = """
import {{ SUFuturesOrderRequestSchema }} from "./sufuturesorderrequest";

const payloads = {payloads};
const out = payloads.map((p: unknown) => SUFuturesOrderRequestSchema.parse(p));
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("npx"), reason="npx not installed")
def test_zod_roundtrip(tmp_path: Path):
    _register_fixtures()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    cfg = Config(
        input_dir=str(out_dir / "in"),
        output_dir=str(out_dir),
        targets=["zod"],
    )
    SchemaGenerationEngine(cfg).generate_all()
    zod_dir = out_dir / "zod"

    (zod_dir / "harness.ts").write_text(
        _ZOD_HARNESS.format(payloads=json.dumps(WIRE_PAYLOADS))
    )

    if (
        subprocess.run(
            ["npm", "init", "-y"],
            cwd=zod_dir,
            capture_output=True,
            text=True,
            timeout=30,
        ).returncode
        != 0
    ):
        pytest.skip("npm init failed")

    install = subprocess.run(
        ["npm", "install", "zod", "typescript", "tsx"],
        cwd=zod_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if install.returncode != 0:
        pytest.skip(f"npm install failed: {install.stderr}")

    result = subprocess.run(
        ["npx", "tsx", "harness.ts"],
        cwd=zod_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"zod harness failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    parsed = json.loads(result.stdout)
    assert len(parsed) == len(WIRE_PAYLOADS)
    for emitted, wire in zip(parsed, WIRE_PAYLOADS, strict=True):
        assert _canonical(emitted) == _canonical(wire)
