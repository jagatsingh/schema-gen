"""Schema Gen configuration file"""

from schema_gen import Config

config = Config(
    input_dir="schemas/",
    output_dir="generated/",
    targets=["pydantic"],
    
    # Pydantic-specific settings
    pydantic={
        "variants": ["create", "update", "response"],
        "use_enum": True,
    },
    
    # SQLAlchemy-specific settings (for future use)
    sqlalchemy={
        "use_declarative": True,
        "naming_convention": "snake_case"
    },
)
