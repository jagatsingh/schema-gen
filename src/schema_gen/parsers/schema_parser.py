"""Parser to convert schema_gen Schema classes to USR format"""

import logging
import warnings
from enum import Enum

from ..core.schema import SchemaRegistry, _extract_meta_attributes
from ..core.usr import FieldType, TypeMapper, USREnum, USRField, USRSchema

# Mapping from target name to the inner meta class name on Enum/Schema
# classes. Mirrors the table in core.schema.Schema().
_ENUM_META_CLASSES = {
    "pydantic": "PydanticMeta",
    "sqlalchemy": "SQLAlchemyMeta",
    "pathway": "PathwayMeta",
    "rust": "SerdeMeta",
}


def _detect_enum_value_type(enum_cls: type) -> type | None:
    """Return the value type of an Enum class when it is ``str``- or
    ``int``-backed.

    Detects both explicit mixin forms (``class Foo(str, Enum)``) and
    stdlib convenience classes (``StrEnum``, ``IntEnum``). Returns
    ``None`` for plain ``Enum`` classes or enums backed by other types.
    """
    if issubclass(enum_cls, str):
        return str
    if issubclass(enum_cls, int):
        return int
    return None


def _build_usr_enum(enum_cls: type) -> USREnum:
    """Construct a USREnum from a Python Enum class, including any
    target-specific meta classes (PydanticMeta, SerdeMeta, ...) the user
    attached as inner classes.
    """
    custom_code: dict[str, dict] = {}
    for target, meta_name in _ENUM_META_CLASSES.items():
        meta = getattr(enum_cls, meta_name, None)
        # An Enum subclass exposes inherited attributes via getattr; only
        # treat the meta as user-supplied when it's a class defined on the
        # enum itself (or one of its bases that is also an Enum subclass).
        if meta is not None and isinstance(meta, type):
            custom_code[target] = _extract_meta_attributes(meta)
    # Only read __doc__ from the enum's own __dict__ to avoid picking up
    # Python's auto-generated "An enumeration." fallback that older
    # versions of the stdlib ``Enum`` metaclass install on subclasses.
    raw_doc = enum_cls.__dict__.get("__doc__")
    docstring = (
        raw_doc.strip() if isinstance(raw_doc, str) and raw_doc.strip() else None
    )
    return USREnum(
        name=enum_cls.__name__,
        values=[(e.name, e.value) for e in enum_cls],
        value_type=_detect_enum_value_type(enum_cls),
        custom_code=custom_code,
        docstring=docstring,
    )


logger = logging.getLogger(__name__)


class SchemaParser:
    """Parses schema_gen Schema classes into USR format"""

    def __init__(self):
        self.type_mapper = TypeMapper()

    def parse_schema(self, schema_class: type) -> USRSchema:
        """Convert a schema_gen Schema class to USR format

        Args:
            schema_class: Class decorated with @Schema

        Returns:
            USRSchema representation
        """
        if not hasattr(schema_class, "_schema_fields"):
            raise ValueError(
                f"Class {schema_class.__name__} is not a valid Schema. Use @Schema decorator."
            )

        # Create USR fields from schema fields
        usr_fields = []
        for field_name, field_data in schema_class._schema_fields.items():
            usr_field = self.type_mapper.create_usr_field_from_python(
                name=field_name,
                python_type=field_data["type"],
                field_info=field_data["field_info"],
            )
            # Discriminated-union resolution. If the field carries a
            # discriminator, look up each union member (must be a registered
            # @Schema class) and pull the Literal[...] value of its
            # matching tag field. Variants without a Literal tag, or where
            # the tag has multiple values, are rejected at parse time so
            # the contract is unambiguous.
            if usr_field.discriminator and usr_field.union_types:
                try:
                    usr_field.union_tag_values = self._resolve_discriminator_tags(
                        usr_field
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"Schema '{schema_class.__name__}', field '{field_name}': "
                        f"discriminator resolution failed — {exc}"
                    ) from exc
            usr_fields.append(usr_field)

        # Discover enum types referenced by fields.
        #
        # Enums can appear at several nesting depths:
        #   Enum                                          -> top-level
        #   Optional[Enum] / Enum | None                  -> inner_type
        #   list[Enum] / set[Enum] / frozenset[Enum]      -> inner_type
        #   Optional[list[Enum]]                          -> inner_type.inner_type
        #   Union[Enum, ...]                              -> union_types
        #   dict[str, Enum]                               -> not currently modeled in USR
        #
        # We walk the field tree recursively so that an enum referenced at any
        # depth contributes its members to ``schema.enums``. Previously the
        # discovery pass only looked at ``usr_field.python_type`` for top-level
        # enum fields, and for ``Optional[Enum]`` that attribute is the wrapped
        # ``Optional[...]`` form rather than the enum class itself, so enum
        # member extraction silently produced an empty list (issue #15).
        seen_enums: dict[str, USREnum] = {}

        def _collect_enum(f: USRField) -> None:
            if f is None:
                return
            if (
                f.type == FieldType.ENUM
                and f.enum_name
                and f.enum_name not in seen_enums
            ):
                pt = f.python_type
                # ``python_type`` is the unwrapped enum class for top-level
                # enum fields and for the recursively-created inner_type of an
                # ``Optional[Enum]`` / ``list[Enum]``. For the *outer* field of
                # an Optional it is the wrapper (e.g. ``Optional[Enum]``), in
                # which case we skip and let recursion into ``inner_type``
                # populate the entry.
                if isinstance(pt, type) and issubclass(pt, Enum):
                    seen_enums[f.enum_name] = _build_usr_enum(pt)
            # Recurse through wrappers: Optional[T], list[T], set[T], Union[...].
            if f.inner_type is not None:
                _collect_enum(f.inner_type)
            for ut in f.union_types:
                _collect_enum(ut)

        for usr_field in usr_fields:
            _collect_enum(usr_field)

        # Sort by name so generated output is deterministic across
        # runs/environments regardless of field declaration order.
        enums = sorted(seen_enums.values(), key=lambda e: e.name)

        # Extract variants if defined
        variants = {}
        if hasattr(schema_class, "Variants"):
            variants_class = schema_class.Variants
            for attr_name in dir(variants_class):
                if not attr_name.startswith("_"):
                    attr_value = getattr(variants_class, attr_name)
                    if isinstance(attr_value, list):
                        variants[attr_name] = attr_value

        # Extract custom code if available
        custom_code = getattr(schema_class, "_custom_code", {})

        usr_schema = USRSchema(
            name=schema_class.__name__,
            fields=usr_fields,
            description=schema_class.__doc__,
            enums=enums,
            variants=variants,
            custom_code=custom_code,
            metadata={},
        )

        # Validate the parsed schema
        issues = usr_schema.validate()
        errors = [i for i in issues if i.severity == "error"]
        warns = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]

        for info in infos:
            logger.info("Schema '%s': %s", usr_schema.name, info.message)

        for warn in warns:
            warnings.warn(
                f"Schema '{usr_schema.name}': {warn.message}",
                stacklevel=2,
            )

        if errors:
            error_msgs = [f"  - {e.message}" for e in errors]
            raise ValueError(
                f"Schema '{usr_schema.name}' has validation errors:\n"
                + "\n".join(error_msgs)
            )

        return usr_schema

    def _resolve_discriminator_tags(self, usr_field: USRField) -> list[str]:
        """For a discriminated-union field, return one Literal[...] tag
        value per union variant.

        Each union variant must be a registered @Schema class with a
        Literal field whose name matches ``usr_field.discriminator`` and
        which has exactly one literal value. Raises ``ValueError`` with a
        helpful message otherwise.
        """
        import typing

        disc = usr_field.discriminator
        tags: list[str] = []
        for variant in usr_field.union_types:
            variant_name = variant.nested_schema or getattr(
                variant.python_type, "__name__", None
            )
            if not variant_name:
                raise ValueError(
                    "union variant has no resolvable schema name "
                    "(only @Schema-decorated classes are supported)"
                )
            variant_cls = SchemaRegistry.get_schema(variant_name)
            if variant_cls is None:
                raise ValueError(
                    f"union variant '{variant_name}' is not a registered @Schema class"
                )
            sf = getattr(variant_cls, "_schema_fields", {}).get(disc)
            if sf is None:
                raise ValueError(
                    f"variant '{variant_name}' has no discriminator field '{disc}'"
                )
            ann = sf["type"]
            # Strip Annotated wrapper if present.
            if typing.get_origin(ann) is typing.Annotated:
                ann = typing.get_args(ann)[0]
            if typing.get_origin(ann) is not typing.Literal:
                raise ValueError(
                    f"variant '{variant_name}' field '{disc}' must be "
                    f"Literal[...] for discriminated unions, got {ann!r}"
                )
            literal_args = typing.get_args(ann)
            if len(literal_args) != 1:
                raise ValueError(
                    f"variant '{variant_name}' field '{disc}' must have "
                    f"exactly one Literal value, got {literal_args!r}"
                )
            tag = literal_args[0]
            if not isinstance(tag, str):
                raise ValueError(
                    f"variant '{variant_name}' field '{disc}' literal value "
                    f"must be a string, got {tag!r}"
                )
            tags.append(tag)
        return tags

    def parse_all_schemas(self) -> list[USRSchema]:
        """Parse all registered schemas to USR format

        Returns:
            List of USRSchema objects for all registered schemas

        Raises:
            ValueError: If any schema has validation errors
        """
        usr_schemas = []
        all_errors = []
        for _schema_name, schema_class in SchemaRegistry.get_all_schemas().items():
            try:
                usr_schema = self.parse_schema(schema_class)
                usr_schemas.append(usr_schema)
            except ValueError as e:
                all_errors.append(str(e))

        if all_errors:
            raise ValueError("Schema validation failed:\n" + "\n".join(all_errors))

        # Sort by schema name so downstream generators emit files and
        # index entries in a stable, environment-independent order.
        usr_schemas.sort(key=lambda s: s.name)
        return usr_schemas

    def parse_schema_by_name(self, schema_name: str) -> USRSchema:
        """Parse a specific schema by name

        Args:
            schema_name: Name of the schema to parse

        Returns:
            USRSchema representation

        Raises:
            ValueError: If schema not found
        """
        schema_class = SchemaRegistry.get_schema(schema_name)
        if schema_class is None:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        return self.parse_schema(schema_class)
