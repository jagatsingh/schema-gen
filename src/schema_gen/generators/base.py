"""Base class for all schema generators"""

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.usr import USRSchema


class BaseGenerator(ABC):
    """Base class for all schema generators.

    All generators must implement generate_file() and generate_model()
    to provide a consistent interface for code generation from USR schemas.

    Subclasses should also define file_extension, generates_index_file,
    and optionally override generate_index() to move file-structure
    knowledge out of the core engine.
    """

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension for generated files (e.g., '.py', '.ts', '.java').

        This includes the leading dot.
        """
        ...

    @property
    def generates_index_file(self) -> bool:
        """Whether this generator produces an index/init file (__init__.py, index.ts, etc.).

        Defaults to False. Override in subclasses that need index files.
        """
        return False

    def get_schema_filename(self, schema: USRSchema) -> str:
        """Return the output filename for a given schema.

        Default: lowercase schema name + file_extension (e.g., 'user_models.py').
        Override in subclasses that use different naming conventions.
        """
        return f"{schema.name.lower()}{self.file_extension}"

    def generate_index(self, schemas: list[USRSchema], output_dir: Path) -> str | None:
        """Generate the content of the index/init file.

        Args:
            schemas: All USR schemas being generated
            output_dir: The target output directory

        Returns:
            The file content as a string, or None if no index file is needed.
        """
        return None

    def get_extra_files(
        self, schemas: list[USRSchema], output_dir: Path
    ) -> dict[str, str]:
        """Return additional files to write beyond per-schema files and the index.

        Returns:
            Dict mapping filename (relative to output_dir) to file content.
            Empty dict by default.
        """
        return {}

    @abstractmethod
    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file for the given schema.

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with all models/variants
        """
        ...

    @abstractmethod
    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a model for a specific schema variant.

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated model code
        """
        ...
