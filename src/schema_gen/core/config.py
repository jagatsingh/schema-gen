"""Configuration system for schema_gen"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Config:
    """Configuration for schema generation

    Example:
        config = Config(
            input_dir="schemas/",
            output_dir="generated/",
            targets=["pydantic", "sqlalchemy"],
            pydantic={"use_enum": True, "extra": "forbid"}
        )
    """

    # Directory configuration
    input_dir: str = "schemas/"
    output_dir: str = "generated/"

    # Target schemas to generate
    targets: list[str] = field(default_factory=lambda: ["pydantic"])

    # Target-specific configuration
    pydantic: dict[str, Any] = field(default_factory=dict)
    sqlalchemy: dict[str, Any] = field(default_factory=dict)
    zod: dict[str, Any] = field(default_factory=dict)
    pathway: dict[str, Any] = field(default_factory=dict)
    dataclasses: dict[str, Any] = field(default_factory=dict)
    typeddict: dict[str, Any] = field(default_factory=dict)
    jsonschema: dict[str, Any] = field(default_factory=dict)
    graphql: dict[str, Any] = field(default_factory=dict)
    protobuf: dict[str, Any] = field(default_factory=dict)
    avro: dict[str, Any] = field(default_factory=dict)
    jackson: dict[str, Any] = field(default_factory=dict)
    kotlin: dict[str, Any] = field(default_factory=dict)

    # Generation settings
    overwrite: bool = True
    add_header: bool = True
    format_code: bool = True

    # Default field behaviors
    defaults: dict[str, Any] = field(
        default_factory=lambda: {
            "nullable_by_default": False,
            "string_max_length": 255,
            "auto_timestamps": True,
        }
    )

    # Custom type mappings
    type_mappings: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, config_path: str = ".schema-gen.config.py") -> "Config":
        """Load configuration from a Python file

        Args:
            config_path: Path to the configuration file

        Returns:
            Config instance
        """
        config_file = Path(config_path)
        if not config_file.exists():
            return cls()  # Return default config

        # Execute the config file and extract the config object
        namespace = {}
        exec(config_file.read_text(), namespace)

        if "config" in namespace:
            return namespace["config"]
        else:
            return cls()  # Return default if no config found
