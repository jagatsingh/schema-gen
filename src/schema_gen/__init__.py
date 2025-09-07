"""
Schema Gen - Universal schema converter for Python

Define schemas once, generate everywhere. Convert between Pydantic, SQLAlchemy, 
Pathway, and other schema formats from a single source of truth.

Example:
    from schema_gen import Schema, Field
    
    @Schema
    class User:
        name: str = Field(max_length=100)
        email: str = Field(format="email")
        age: int | None = Field(default=None)
"""

from .core.schema import Schema, Field
from .core.config import Config

__version__ = "0.1.0"
__all__ = ["Schema", "Field", "Config", "__version__"]
