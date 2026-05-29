"""Cross-language round-trip tests for discriminated (tagged) unions.

A discriminated union — ``Annotated[Union[A, B], Field(discriminator="...")]``
on the Python side — must serialize to ONE canonical wire format and round-trip
identically across every target schema-gen emits:

* **Pydantic v2** — ``Annotated[Union[...], Field(discriminator=...)]``
* **Rust / serde** — internally-tagged enum (``#[serde(tag = "...")]``)
* **Zod** — ``z.discriminatedUnion("...", [...])``
* **JSON Schema** — ``oneOf`` + an OpenAPI-style ``discriminator`` object

The chosen wire representation is **internally tagged**: the discriminator key
lives *inside* the variant object alongside its other fields, e.g.::

    {"instrument_type": "futures", "contract": "ESZ5"}

serde's internally-tagged enum, Pydantic's discriminated union, and Zod's
discriminated union all agree on exactly this shape, which is why it is the
representation schema-gen targets (rather than externally- or adjacently-tagged).

This is the highest-leverage union test: a single canonical JSON payload is
fed through every generated artefact and each is asserted to produce a
byte-identical (key-sorted) re-serialization, proving genuine interop rather
than four independent "looks plausible" string checks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Literal

import pytest

from schema_gen import Field, Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

# -----------------------------------------------------------------------
# Schema fixtures — module-level for forward-reference resolution
# -----------------------------------------------------------------------


@Schema
class RTFuturesSpec:
    """Futures variant — discriminator value "futures"."""

    instrument_type: Literal["futures"]
    contract: str


@Schema
class RTOptionsSpec:
    """Options variant — discriminator value "options"."""

    instrument_type: Literal["options"]
    strike: float


@Schema
class RTTradeOrder:
    """trade_spec-style discriminated union keyed on instrument_type."""

    spec: Annotated[
        RTFuturesSpec | RTOptionsSpec, Field(discriminator="instrument_type")
    ]


# Two canonical wire payloads — one per variant. Key order is irrelevant on
# the wire (objects are unordered); we compare structurally after json.loads.
# NOTE: ``strike`` is deliberately non-integral (5000.25, not 5000.0).
# JavaScript has a single Number type, so JSON.stringify renders 5000.0 as
# "5000" — a numeric-formatting artifact unrelated to union dispatch that
# would otherwise make the Zod structural comparison spuriously fail. A
# non-integral value round-trips identically across Python/Rust/Zod.
WIRE_FUTURES = {"spec": {"instrument_type": "futures", "contract": "ESZ5"}}
WIRE_OPTIONS = {"spec": {"instrument_type": "options", "strike": 5000.25}}
WIRE_PAYLOADS = [WIRE_FUTURES, WIRE_OPTIONS]


def _canonical(obj: dict) -> str:
    """Deterministic, structural JSON encoding for cross-language equality."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


@pytest.fixture(autouse=True)
def _register_schemas():
    SchemaRegistry._schemas.clear()
    for cls in (RTFuturesSpec, RTOptionsSpec, RTTradeOrder):
        SchemaRegistry.register(cls)
    yield
    SchemaRegistry._schemas.clear()


# -----------------------------------------------------------------------
# Generator-output shape (fast, no toolchain required)
# -----------------------------------------------------------------------


class TestDiscriminatedUnionShape:
    """Each generator emits the discriminated-union construct, not a blob."""

    def test_rust_internally_tagged_enum(self):
        usr = SchemaParser().parse_schema(RTTradeOrder)
        out = RustGenerator().generate_file(usr)
        assert '#[serde(tag = "instrument_type")]' in out
        assert "pub enum RTTradeOrderSpec {" in out
        assert "Futures(RTFuturesSpec)" in out
        assert "Options(RTOptionsSpec)" in out
        assert "pub spec: RTTradeOrderSpec," in out
        # Must NOT degrade to an untyped blob.
        assert "serde_json::Value" not in out.split("pub spec:")[1].split(",")[0]

    def test_zod_discriminated_union(self):
        usr = SchemaParser().parse_schema(RTTradeOrder)
        out = ZodGenerator().generate_file(usr)
        assert (
            'z.discriminatedUnion("instrument_type", '
            "[RTFuturesSpecSchema, RTOptionsSpecSchema])"
        ) in out
        assert "z.union([" not in out  # plain union would lose discrimination

    def test_jsonschema_oneof_plus_discriminator(self):
        usr = SchemaParser().parse_schema(RTTradeOrder)
        doc = json.loads(JsonSchemaGenerator().generate_file(usr))
        spec = doc["$defs"]["RTTradeOrder"]["properties"]["spec"]
        assert "oneOf" in spec
        assert "anyOf" not in spec  # mutually exclusive, not "any"
        assert spec["discriminator"] == {"propertyName": "instrument_type"}
        assert len(spec["oneOf"]) == 2


# -----------------------------------------------------------------------
# Python / Pydantic round-trip (always runs)
# -----------------------------------------------------------------------


class TestPydanticRoundTrip:
    """The generated Pydantic model parses and re-emits the canonical wire."""

    def _build_models(self, tmp_path: Path):
        import importlib.util
        import sys

        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cfg = Config(
            input_dir=str(out_dir / "in"),
            output_dir=str(out_dir),
            targets=["pydantic"],
        )
        SchemaGenerationEngine(cfg).generate_all()
        pydantic_dir = out_dir / "pydantic"

        # Import the whole generated package so every variant model is in
        # scope, then rebuild the union model to resolve its string
        # forward-references (``Annotated[Union["RTFuturesSpec", ...]]``).
        pkg_name = "_rt_pydantic_pkg"
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name,
            pydantic_dir / "__init__.py",
            submodule_search_locations=[str(pydantic_dir)],
        )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg_mod
        self._loaded_pkg_prefix = pkg_name
        pkg_spec.loader.exec_module(pkg_mod)
        order_cls = pkg_mod.RTTradeOrder
        order_cls.model_rebuild(
            _types_namespace={
                "RTFuturesSpec": pkg_mod.RTFuturesSpec,
                "RTOptionsSpec": pkg_mod.RTOptionsSpec,
            }
        )
        return order_cls

    def teardown_method(self):
        import sys

        prefix = getattr(self, "_loaded_pkg_prefix", None)
        if prefix:
            for key in [k for k in sys.modules if k.startswith(prefix)]:
                sys.modules.pop(key, None)

    @pytest.mark.parametrize("wire", WIRE_PAYLOADS)
    def test_pydantic_roundtrip(self, tmp_path: Path, wire: dict):
        TradeOrder = self._build_models(tmp_path)
        obj = TradeOrder.model_validate(wire)
        emitted = json.loads(obj.model_dump_json())
        assert _canonical(emitted) == _canonical(wire)


# -----------------------------------------------------------------------
# Rust round-trip — compile a tiny harness, deserialize + re-serialize
# -----------------------------------------------------------------------

_RUST_MAIN = r"""
use generated::RTTradeOrder;
use std::io::Read;

fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    // Deserialize each line, re-serialize, print one JSON per line.
    for line in input.lines().filter(|l| !l.trim().is_empty()) {
        let parsed: RTTradeOrder = serde_json::from_str(line).unwrap();
        let out = serde_json::to_string(&parsed).unwrap();
        println!("{}", out);
    }
}
"""


@pytest.mark.skipif(not shutil.which("cargo"), reason="cargo not installed")
def test_rust_roundtrip(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    cfg = Config(
        input_dir=str(out_dir / "in"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    SchemaGenerationEngine(cfg).generate_all()
    rust_dir = out_dir / "rust"

    # Build a binary crate that depends on the generated lib as a module.
    crate = tmp_path / "rt_crate"
    src = crate / "src"
    src.mkdir(parents=True)

    # Re-home the generated files: lib.rs + per-schema modules under src/.
    for rs in rust_dir.glob("*.rs"):
        shutil.copy(rs, src / rs.name)
    # Rename lib.rs content into a module tree the binary can import.
    lib_src = (src / "lib.rs").read_text()
    (src / "lib.rs").write_text(lib_src)
    (src / "main.rs").write_text(_RUST_MAIN)

    cargo_toml = (
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
    (crate / "Cargo.toml").write_text(cargo_toml)

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
    assert len(lines) == len(WIRE_PAYLOADS), f"unexpected output: {result.stdout!r}"
    for emitted_line, wire in zip(lines, WIRE_PAYLOADS, strict=True):
        assert _canonical(json.loads(emitted_line)) == _canonical(wire)


# -----------------------------------------------------------------------
# Zod round-trip — parse + re-serialize via a compiled-then-run TS harness
# -----------------------------------------------------------------------

_ZOD_HARNESS = """
import {{ RTTradeOrderSchema }} from "./rttradeorder";

const payloads = {payloads};
const out = payloads.map((p: unknown) => RTTradeOrderSchema.parse(p));
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("npx"), reason="npx not installed")
def test_zod_roundtrip(tmp_path: Path):
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


# -----------------------------------------------------------------------
# JSON Schema validation — the canonical wire must validate against oneOf
# -----------------------------------------------------------------------


def test_jsonschema_validates_wire(tmp_path: Path):
    jsonschema = pytest.importorskip("jsonschema")

    usr = SchemaParser().parse_schema(RTTradeOrder)
    fut_usr = SchemaParser().parse_schema(RTFuturesSpec)
    opt_usr = SchemaParser().parse_schema(RTOptionsSpec)

    order_doc = json.loads(JsonSchemaGenerator().generate_file(usr))
    fut_doc = json.loads(JsonSchemaGenerator().generate_file(fut_usr))
    opt_doc = json.loads(JsonSchemaGenerator().generate_file(opt_usr))

    # Inline the variant $defs so the spec field's $ref targets resolve
    # without a network/file resolver.
    spec = order_doc["$defs"]["RTTradeOrder"]["properties"]["spec"]
    spec["oneOf"] = [
        fut_doc["$defs"]["RTFuturesSpec"],
        opt_doc["$defs"]["RTOptionsSpec"],
    ]
    schema = order_doc["$defs"]["RTTradeOrder"]

    for wire in WIRE_PAYLOADS:
        jsonschema.validate(instance=wire, schema=schema)

    # A payload with an unknown discriminator must fail validation.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"spec": {"instrument_type": "swaps", "x": 1}},
            schema=schema,
        )
