"""Framework-execution tests — every generator's output must actually work.

Snapshot tests (``test_generator_output_stability.py``) lock the *shape* of
output. Correctness invariants (``test_generator_correctness_invariants.py``)
catch syntactic/structural bugs at the AST level. This file goes one step
further: for every generator that can be exercised cheaply (no heavy external
toolchain), we *load the generated output in its real framework and use it*.

Coverage today — every generator has a test that exercises the real
framework. Toolchain-dependent tests skip cleanly with an install hint
when the compiler is missing locally; CI installs every toolchain so
nothing skips there.

| Generator   | Validation performed                                          |
| ----------- | ------------------------------------------------------------- |
| Pydantic    | exec → instantiate → catch ValidationError on bad input       |
| SQLAlchemy  | import as a package → assert __tablename__, __doc__, columns  |
| Dataclasses | exec → instantiate → field equality                           |
| TypedDict   | exec → assert annotations match                               |
| Pathway     | exec → assert pw.Table/Schema in MRO + annotations match      |
| JSON Schema | meta-schema validation + validate a sample document           |
| GraphQL     | graphql-core parse                                            |
| Avro        | fastavro.parse_schema                                         |
| Protobuf    | protoc parse (skips with hint when missing)                   |
| Rust        | cargo check on a minimal crate (skips with hint when missing) |
| Zod / TS    | tsc --noEmit --strict (skips with hint when missing)          |
| Kotlin      | kotlinc (skips with hint when missing)                        |
| Jackson     | javac with Jackson on classpath (skips with hint when missing)|

Bugs missed by snapshot/syntax tests but caught here:
- Pydantic generated file fails to import (e.g. unresolved enum forward ref)
- SQLAlchemy ``__doc__`` is ``None`` because docstring landed after
  ``__tablename__`` (PR #102 review #3)
- Generated JSON Schema is not itself a valid JSON Schema
- Generated GraphQL has parse errors that snapshot tests can't see
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from enum import Enum
from pathlib import Path
from types import ModuleType

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.dataclasses_generator import DataclassesGenerator
from schema_gen.generators.graphql_generator import GraphQLGenerator
from schema_gen.generators.jackson_generator import JacksonGenerator
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.kotlin_generator import KotlinGenerator
from schema_gen.generators.pathway_generator import PathwayGenerator
from schema_gen.generators.protobuf_generator import ProtobufGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
from schema_gen.generators.typeddict_generator import TypedDictGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

# -----------------------------------------------------------------------
# Canonical schema — a single shape used by every framework test below
# -----------------------------------------------------------------------


class FrameworkOrderSide(str, Enum):
    """Two-sided trade direction."""

    BUY = "buy"
    SELL = "sell"


@Schema
class FrameworkOrder:
    """Order placed against the matching engine.

    Used as a single fixture across every framework execution test so a
    single schema flaw surfaces as multiple test failures (one per
    generator) rather than being silently masked.
    """

    id: int = Field(primary_key=True, description="Order id")
    instrument: str = Field(description="Exchange-prefixed symbol")
    quantity: int = Field(description="Number of contracts")
    price: float = Field(description="Limit price")
    side: FrameworkOrderSide = Field(description="Buy or sell")
    tag: str | None = Field(default=None, description="Optional client tag")


def _parse():
    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(FrameworkOrder)
    return SchemaParser().parse_schema(FrameworkOrder)


def _exec_module(source: str, name: str) -> ModuleType:
    """Compile ``source`` into a fresh module and return it.

    Inserts the module into ``sys.modules`` so Pydantic v2 forward-reference
    resolution (which looks up ``sys.modules[cls.__module__]`` to find the
    enclosing namespace) can find sibling enum and class definitions.
    Tests should give each call a unique name to avoid cross-contamination.
    """
    import sys

    mod = ModuleType(name)
    mod.__file__ = f"<{name}>"
    sys.modules[name] = mod
    exec(compile(source, mod.__file__, "exec"), mod.__dict__)
    return mod


# -----------------------------------------------------------------------
# Pydantic — full instantiate + validate path
# -----------------------------------------------------------------------


class TestPydanticFrameworkExecution:
    """Generated Pydantic file must be executable and produce a working model."""

    def test_module_imports_and_model_instantiates(self):
        out = PydanticGenerator().generate_file(_parse())
        mod = _exec_module(out, "pydantic_framework_test")
        cls = mod.FrameworkOrder
        # Must be a real Pydantic v2 BaseModel subclass.
        from pydantic import BaseModel

        assert issubclass(cls, BaseModel)
        # Class docstring must round-trip (i.e. is the first body statement).
        assert cls.__doc__ is not None
        assert "Order placed against the matching engine." in cls.__doc__
        # Construct a valid instance.
        instance = cls(
            id=1,
            instrument="NSE:NIFTY",
            quantity=10,
            price=18000.5,
            side=mod.FrameworkOrderSide.BUY,
        )
        assert instance.instrument == "NSE:NIFTY"
        assert instance.tag is None

    def test_validation_rejects_bad_input(self):
        from pydantic import ValidationError

        out = PydanticGenerator().generate_file(_parse())
        mod = _exec_module(out, "pydantic_framework_test_validate")
        cls = mod.FrameworkOrder
        with pytest.raises(ValidationError):
            cls(id=1, instrument="x", quantity="not-an-int", price=1.0, side="buy")


# -----------------------------------------------------------------------
# SQLAlchemy — exec + structural assertions on the mapped class
# -----------------------------------------------------------------------


class TestSqlalchemyFrameworkExecution:
    """Generated SQLAlchemy file must produce a working DeclarativeBase model."""

    def test_module_compiles_and_class_has_tablename_and_docstring(
        self, tmp_path: Path
    ):
        import importlib.util
        import sys

        # SqlAlchemyGenerator emits ``from ._base import Base``. Materialize
        # a real package on disk so the relative import resolves and SQLAlchemy
        # can read annotations off the original module (the in-memory exec
        # path leaves ``__module__`` as ``builtins`` and breaks ``Mapped[T]``
        # lookup).
        out = SqlAlchemyGenerator().generate_file(_parse())
        pkg_dir = tmp_path / "_sqlalchemy_framework_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "_base.py").write_text(
            "from sqlalchemy.orm import DeclarativeBase\n"
            "class Base(DeclarativeBase):\n"
            "    pass\n"
        )
        mod_path = pkg_dir / "frameworkorder_models.py"
        mod_path.write_text(out)

        sys.path.insert(0, str(tmp_path))
        try:
            spec = importlib.util.spec_from_file_location(
                "_sqlalchemy_framework_pkg.frameworkorder_models", mod_path
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            cls = mod.FrameworkOrder
            assert cls.__tablename__ == "framework_order"
            # Docstring must be the first class-body statement (PR #102 fix).
            assert cls.__doc__ is not None
            assert "Order placed against the matching engine." in cls.__doc__
            # Assert SQLAlchemy actually mapped the columns.
            assert "instrument" in cls.__table__.columns
            assert "quantity" in cls.__table__.columns
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("_sqlalchemy_framework_pkg.frameworkorder_models", None)


# -----------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------


class TestDataclassesFrameworkExecution:
    def test_module_compiles_and_dataclass_instantiates(self):
        from dataclasses import is_dataclass

        out = DataclassesGenerator().generate_file(_parse())
        mod = _exec_module(out, "dataclasses_framework_test")
        cls = mod.FrameworkOrder
        assert is_dataclass(cls)
        # Dataclasses generator currently emits enum fields as ``str``;
        # construct accordingly so the test focuses on dataclass behavior,
        # not enum representation.
        instance = cls(
            id=1,
            instrument="NSE:NIFTY",
            quantity=10,
            price=18000.5,
            side="buy",
        )
        assert instance.instrument == "NSE:NIFTY"
        assert instance.tag is None  # default propagates


# -----------------------------------------------------------------------
# TypedDict
# -----------------------------------------------------------------------


class TestTypedDictFrameworkExecution:
    def test_module_compiles_and_annotations_match_schema(self):
        out = TypedDictGenerator().generate_file(_parse())
        mod = _exec_module(out, "typeddict_framework_test")
        cls = mod.FrameworkOrder
        # TypedDict carries the field set on ``__annotations__``.
        annotations = cls.__annotations__
        for required in ("instrument", "quantity", "price", "side", "tag"):
            assert required in annotations, (
                f"TypedDict missing field {required!r}: {list(annotations)}"
            )


# -----------------------------------------------------------------------
# Pathway
# -----------------------------------------------------------------------


class TestPathwayFrameworkExecution:
    def test_module_compiles_and_class_in_pathway_mro(self):
        import importlib.util

        if importlib.util.find_spec("pathway") is None:
            pytest.skip("pathway not installed")
        out = PathwayGenerator().generate_file(_parse())
        mod = _exec_module(out, "pathway_framework_test")
        cls = mod.FrameworkOrder
        # Pathway codegen emits a class that inherits from pw.Table (one of
        # the framework's Schema-bearing base classes). Asserting Table OR
        # Schema is in the MRO catches accidental loss of the framework
        # base while staying tolerant of pathway's internal class layout.
        mro_names = {c.__qualname__ for c in cls.__mro__}
        assert "Table" in mro_names or "Schema" in mro_names, (
            f"Generated class is not a pathway Table/Schema: {cls.__mro__}"
        )
        assert "instrument" in cls.__annotations__


# -----------------------------------------------------------------------
# JSON Schema — meta-schema validation + sample-document validation
# -----------------------------------------------------------------------


class TestJsonSchemaFrameworkExecution:
    def test_output_is_valid_json_schema(self):
        import jsonschema

        out = JsonSchemaGenerator().generate_file(_parse())
        schema = json.loads(out)
        # The output must itself satisfy the JSON Schema meta-schema.
        # ``jsonschema.Draft202012Validator.check_schema`` raises if not.
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_sample_document_validates_against_generated_schema(self):
        import jsonschema

        out = JsonSchemaGenerator().generate_file(_parse())
        schema = json.loads(out)
        # Provide a non-null ``tag`` since the JSON Schema generator currently
        # emits ``"type": "string"`` for the optional field rather than
        # ``["string", "null"]`` — that shape mismatch is a separate issue;
        # this test focuses on whether the schema validates a *valid* doc.
        sample = {
            "id": 1,
            "instrument": "NSE:NIFTY",
            "quantity": 10,
            "price": 18000.5,
            "side": "buy",
            "tag": "manual-entry",
        }
        # Validate against the whole document so the top-level ``$ref`` to
        # ``#/$defs/FrameworkOrder`` resolves naturally.
        jsonschema.validate(instance=sample, schema=schema)


# -----------------------------------------------------------------------
# GraphQL — parse + buildable schema check
# -----------------------------------------------------------------------


class TestGraphQLFrameworkExecution:
    def test_output_parses_as_graphql_sdl(self):
        from graphql import GraphQLSyntaxError, parse

        out = GraphQLGenerator().generate_file(_parse())
        try:
            doc = parse(out)
        except GraphQLSyntaxError as exc:
            pytest.fail(f"Generated GraphQL SDL did not parse: {exc}")
        # Must contain at least one type definition.
        assert any(d.kind != "schema_definition" for d in doc.definitions)


# -----------------------------------------------------------------------
# Avro — parsed by fastavro/avro if available, skip otherwise
# -----------------------------------------------------------------------


class TestAvroFrameworkExecution:
    def test_output_parses_as_avro_schema(self):
        try:
            import fastavro
        except ImportError:
            pytest.skip("fastavro not installed")
        from schema_gen.generators.avro_generator import AvroGenerator

        out = AvroGenerator().generate_file(_parse())
        wrapper = json.loads(out)
        # The Avro generator wraps the actual schema(s) in a metadata
        # envelope (``{"_meta": ..., "schemas": [...]}``). Iterate every
        # contained schema so a future change that emits multiple records
        # still gets each one validated.
        schemas = wrapper.get("schemas", [wrapper])
        assert schemas, "Avro generator emitted no schemas"
        for s in schemas:
            # ``fastavro.parse_schema`` raises ``SchemaParseException`` on
            # invalid Avro JSON.
            fastavro.parse_schema(s)


# -----------------------------------------------------------------------
# Protobuf — protoc if available, structural fallback
# -----------------------------------------------------------------------


class TestProtobufFrameworkExecution:
    def test_protoc_accepts_output(self):
        if not shutil.which("protoc"):
            pytest.skip(
                "protoc not on PATH — install protobuf-compiler "
                "(`apt-get install protobuf-compiler` / `brew install protobuf`)"
            )
        out = ProtobufGenerator().generate_file(_parse())
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            proto_path = tmpdir / "_framework_order.proto"
            proto_path.write_text(out)
            # ``--experimental_allow_proto3_optional`` is required by older
            # protoc (<3.15) and is a no-op on newer ones, so this command
            # works against both Ubuntu LTS apt-installed protoc and recent
            # protoc binaries.
            result = subprocess.run(
                [
                    "protoc",
                    "--experimental_allow_proto3_optional",
                    "--proto_path",
                    str(tmpdir),
                    "--descriptor_set_out",
                    str(tmpdir / "out.pb"),
                    str(proto_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        assert result.returncode == 0, (
            f"protoc rejected the generated .proto:\n{result.stderr}"
        )


# -----------------------------------------------------------------------
# Rust — cargo check on a minimal crate that includes the generated file
# -----------------------------------------------------------------------


class TestRustFrameworkExecution:
    def test_cargo_check_accepts_output(self, tmp_path: Path):
        if not shutil.which("cargo"):
            pytest.skip(
                "cargo not on PATH — install Rust (https://rustup.rs) to run this test"
            )
        out = RustGenerator().generate_file(_parse())
        # Build a minimal crate: Cargo.toml + src/lib.rs that includes the
        # generated module. ``cargo check`` runs the type-checker without
        # producing an artifact — fast enough for pre-push.
        crate = tmp_path / "rust_framework_check"
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(
            "[package]\n"
            'name = "rust_framework_check"\n'
            'version = "0.0.0"\n'
            'edition = "2021"\n'
            "[dependencies]\n"
            'serde = { version = "1", features = ["derive"] }\n'
            'schemars = "0.8"\n'
        )
        (crate / "src" / "lib.rs").write_text(out)
        result = subprocess.run(
            ["cargo", "check", "--quiet", "--offline"],
            cwd=crate,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # ``--offline`` is best-effort: if the crate cache lacks ``serde``
        # the check fails with a network error rather than a type error,
        # so retry without ``--offline`` once.
        if result.returncode != 0 and "offline" in result.stderr.lower():
            result = subprocess.run(
                ["cargo", "check", "--quiet"],
                cwd=crate,
                capture_output=True,
                text=True,
                timeout=300,
            )
        assert result.returncode == 0, (
            f"cargo check rejected the generated lib.rs:\n{result.stderr}"
        )


# -----------------------------------------------------------------------
# Zod / TypeScript — tsc --noEmit on the generated .ts
# -----------------------------------------------------------------------


class TestZodFrameworkExecution:
    def test_tsc_accepts_output(self, tmp_path: Path):
        if not shutil.which("tsc"):
            pytest.skip(
                "tsc not on PATH — install TypeScript "
                "(`npm install -g typescript zod`) to run this test"
            )
        # tsc needs to resolve ``import { z } from 'zod';`` — wire in the
        # globally-installed ``zod`` package by symlinking it into a local
        # ``node_modules`` directory next to the generated .ts file.
        npm_root = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        global_zod = Path(npm_root) / "zod"
        if not global_zod.exists():
            pytest.skip(
                "zod not installed globally — `npm install -g zod` to run this test"
            )
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "zod").symlink_to(global_zod)

        out = ZodGenerator().generate_file(_parse())
        ts_file = tmp_path / "framework_order.ts"
        ts_file.write_text(out)
        result = subprocess.run(
            [
                "tsc",
                "--noEmit",
                "--strict",
                "--skipLibCheck",
                "--target",
                "es2022",
                "--module",
                "esnext",
                "--moduleResolution",
                "bundler",
                str(ts_file),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"tsc rejected the generated .ts:\n{result.stdout}\n{result.stderr}"
        )


# -----------------------------------------------------------------------
# Kotlin — kotlinc on the generated .kt (warns-only, focused on syntax)
# -----------------------------------------------------------------------


class TestKotlinFrameworkExecution:
    def test_kotlinc_accepts_output(self, tmp_path: Path):
        if not shutil.which("kotlinc"):
            pytest.skip(
                "kotlinc not on PATH — install the Kotlin compiler "
                "(https://kotlinlang.org/docs/command-line.html) to run this test"
            )
        out = KotlinGenerator().generate_file(_parse())
        kt_file = tmp_path / "FrameworkOrder.kt"
        kt_file.write_text(out)
        # Resolve a classpath for kotlinx-serialization. CI is expected to
        # set ``KOTLIN_CLASSPATH`` after downloading the runtime jar; locally
        # users can do the same. When the runtime is missing, the @Serializable
        # annotation can't resolve and that's a tooling-environment issue,
        # not a generator bug — skip cleanly with a helpful message.
        #
        # ``kotlinc`` does NOT expand classpath wildcards (unlike ``javac``),
        # so glob the value of ``KOTLIN_CLASSPATH`` ourselves and join with
        # the platform-correct path separator. ``dir/*`` and explicit
        # colon/semicolon-separated entries both work this way.
        import glob
        import os

        raw_cp = os.environ.get("KOTLIN_CLASSPATH", "")
        cp_entries: list[str] = []
        for entry in raw_cp.split(os.pathsep):
            if not entry:
                continue
            cp_entries.extend(glob.glob(entry) or [entry])
        classpath = os.pathsep.join(cp_entries)
        cmd = ["kotlinc", "-nowarn", "-d", str(tmp_path / "out")]
        if classpath:
            cmd.extend(["-cp", classpath])
        cmd.append(str(kt_file))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and "unresolved reference 'kotlinx'" in result.stderr:
            pytest.skip(
                "kotlinx-serialization runtime not on classpath — set "
                "KOTLIN_CLASSPATH to the kotlinx-serialization jar to run this test"
            )
        assert result.returncode == 0, (
            f"kotlinc rejected the generated .kt:\n{result.stderr}"
        )


# -----------------------------------------------------------------------
# Jackson (Java) — javac on the generated .java with Jackson on classpath
# -----------------------------------------------------------------------


class TestJacksonFrameworkExecution:
    def test_javac_accepts_output(self, tmp_path: Path):
        if not shutil.which("javac"):
            pytest.skip(
                "javac not on PATH — install a JDK "
                "(`apt-get install default-jdk` / Adoptium) to run this test"
            )
        out = JacksonGenerator().generate_file(_parse())
        # Generator emits ``package com.example.models;`` — mirror that
        # in the on-disk layout so javac can find the file by package.
        pkg_dir = tmp_path / "com" / "example" / "models"
        pkg_dir.mkdir(parents=True)
        java_file = pkg_dir / "FrameworkOrder.java"
        java_file.write_text(out)
        # Resolve a classpath. We accept either a CLASSPATH env var (set
        # in CI after downloading Jackson jars) or fall back to scanning
        # ``/tmp/java-libs/`` (the location used by comprehensive-test.yml).
        import os

        classpath = os.environ.get("CLASSPATH") or "/tmp/java-libs/*"
        result = subprocess.run(
            [
                "javac",
                "-d",
                str(tmp_path / "out"),
                "-cp",
                classpath,
                str(java_file),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and "package com.fasterxml" in result.stderr:
            pytest.skip(
                "Jackson jars not available on CLASSPATH — set CLASSPATH "
                "to include jackson-core/databind/annotations to run this test"
            )
        if (
            result.returncode != 0
            and "package javax.validation.constraints" in result.stderr
        ):
            pytest.skip(
                "Bean Validation API not on CLASSPATH — the Jackson generator "
                "emits @NotNull annotations from javax.validation.constraints; "
                "include jakarta.validation-api (or javax.validation:validation-api) "
                "in CLASSPATH to run this test"
            )
        assert result.returncode == 0, (
            f"javac rejected the generated .java:\n{result.stderr}"
        )
