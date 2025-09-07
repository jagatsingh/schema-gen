"""Configuration system for schema_gen"""

from typing import Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Config:
    """Configuration for schema generation
    
    Example:
        config = Config(
            input_dir="schemas/",
            output_dir="generated/",
            targets=["pydantic", "sqlalchemy"],
            pydantic={"variants": ["create", "update", "response"]}
        )
    """
    
    # Directory configuration
    input_dir: str = "schemas/"
    output_dir: str = "generated/"
    
    # Target schemas to generate
    targets: List[str] = field(default_factory=lambda: ["pydantic"])
    
    # Target-specific configuration
    pydantic: Dict[str, Any] = field(default_factory=dict)
    sqlalchemy: Dict[str, Any] = field(default_factory=dict)
    pathway: Dict[str, Any] = field(default_factory=dict)
    
    # Generation settings
    overwrite: bool = True
    add_header: bool = True
    format_code: bool = True
    
    # Default field behaviors
    defaults: Dict[str, Any] = field(default_factory=lambda: {
        'nullable_by_default': False,
        'string_max_length': 255,
        'auto_timestamps': True
    })
    
    # Custom type mappings
    type_mappings: Dict[str, Dict[str, str]] = field(default_factory=dict)
    
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
        
        if 'config' in namespace:
            return namespace['config']
        else:
            return cls()  # Return default if no config found