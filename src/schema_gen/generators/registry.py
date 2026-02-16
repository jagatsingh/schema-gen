"""Generator registry mapping target names to generator classes"""

from .avro_generator import AvroGenerator
from .dataclasses_generator import DataclassesGenerator
from .graphql_generator import GraphQLGenerator
from .jackson_generator import JacksonGenerator
from .jsonschema_generator import JsonSchemaGenerator
from .kotlin_generator import KotlinGenerator
from .pathway_generator import PathwayGenerator
from .protobuf_generator import ProtobufGenerator
from .pydantic_generator import PydanticGenerator
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
}

# Maps target names to their file-writing method name on SchemaGenerationEngine
TARGET_FILE_METHODS: dict[str, str] = {
    "pydantic": "_generate_pydantic_files",
    "sqlalchemy": "_generate_sqlalchemy_files",
    "zod": "_generate_zod_files",
    "pathway": "_generate_python_files",
    "dataclasses": "_generate_python_files",
    "typeddict": "_generate_python_files",
    "jsonschema": "_generate_json_files",
    "graphql": "_generate_graphql_files",
    "protobuf": "_generate_protobuf_files",
    "avro": "_generate_avro_files",
    "jackson": "_generate_jackson_files",
    "kotlin": "_generate_kotlin_files",
}

# Targets that use the generic _generate_python_files method (need target_name arg)
PYTHON_FILE_TARGETS = {"pathway", "dataclasses", "typeddict"}
