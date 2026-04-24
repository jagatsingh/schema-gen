"""Generator registry mapping target names to generator classes"""

from .avro_generator import AvroGenerator
from .dataclasses_generator import DataclassesGenerator
from .docs_generator import DocsGenerator
from .graphql_generator import GraphQLGenerator
from .jackson_generator import JacksonGenerator
from .jsonschema_generator import JsonSchemaGenerator
from .kotlin_generator import KotlinGenerator
from .pathway_generator import PathwayGenerator
from .protobuf_generator import ProtobufGenerator
from .pydantic_generator import PydanticGenerator
from .rust_generator import RustGenerator
from .sqlalchemy_generator import SqlAlchemyGenerator
from .typeddict_generator import TypedDictGenerator
from .zod_generator import ZodGenerator

GENERATOR_REGISTRY: dict[str, type] = {
    "pydantic": PydanticGenerator,
    "sqlalchemy": SqlAlchemyGenerator,
    "zod": ZodGenerator,
    "pathway": PathwayGenerator,
    "dataclasses": DataclassesGenerator,
    "typeddict": TypedDictGenerator,
    "jsonschema": JsonSchemaGenerator,
    "graphql": GraphQLGenerator,
    "protobuf": ProtobufGenerator,
    "avro": AvroGenerator,
    "jackson": JacksonGenerator,
    "kotlin": KotlinGenerator,
    "rust": RustGenerator,
    "docs": DocsGenerator,
}
