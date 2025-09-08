#!/usr/bin/env python3
"""
Example demonstrating target-specific Meta classes (PydanticMeta, SQLAlchemyMeta)

This example shows the new approach with target-specific meta classes,
while maintaining backward compatibility with the legacy Meta class.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime

from schema_gen import Field, Schema


@Schema
class BasicPydanticExample:
    """Example using only PydanticMeta (clean approach)"""

    price: float = Field(description="Product price")
    name: str = Field(description="Product name")

    class PydanticMeta:
        imports = ["import math", "from pydantic import field_validator"]

        raw_code = """
    @field_validator("price", mode="before")
    def validate_price(cls, value) -> float:
        if isinstance(value, str) and value.lower() == 'nan':
            return 0.0
        return float(value)"""

        methods = '''
    def format_price(self) -> str:
        return f"${self.price:.2f}"'''


@Schema
class TargetSpecificMetaExample:
    """Example using target-specific Meta classes"""

    # Common fields
    id: int = Field(primary_key=True, description="Unique identifier")
    name: str = Field(min_length=1, max_length=100, description="Product name")
    price: float = Field(min_value=0, description="Price")
    category: str = Field(description="Product category")
    stock_quantity: int = Field(min_value=0, default=0, description="Stock")
    is_active: bool = Field(default=True, description="Active status")
    created_at: datetime = Field(auto_now_add=True, description="Creation time")

    # Pydantic-specific customizations
    class PydanticMeta:
        imports = [
            "import math",
            "from pydantic import field_validator",
            "from decimal import Decimal",
        ]

        raw_code = '''
    @field_validator("price", mode="before")
    def clean_price(cls, value) -> float:
        """Clean price data from various sources"""
        if value is None:
            return 0.0
        if isinstance(value, str):
            if value.lower() in ['nan', 'inf', '-inf', 'n/a', '']:
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return float(value)
        return 0.0

    @field_validator("name", mode="after")
    def validate_name(cls, value):
        """Ensure name is properly formatted"""
        return value.strip().title()'''

        methods = '''
    def calculate_total_value(self) -> float:
        """Calculate total inventory value"""
        return self.price * self.stock_quantity

    def is_in_stock(self) -> bool:
        """Check if product is in stock"""
        return self.stock_quantity > 0 and self.is_active

    def get_display_info(self) -> dict:
        """Get formatted info for display"""
        return {
            "id": self.id,
            "name": self.name,
            "price": f"${self.price:.2f}",
            "category": self.category,
            "stock_status": "In Stock" if self.is_in_stock() else "Out of Stock",
            "total_value": f"${self.calculate_total_value():.2f}"
        }'''

    # Future: SQLAlchemy-specific customizations
    class SQLAlchemyMeta:
        # This will be used when SQLAlchemy generator is implemented
        table_name = "products"
        indexes = [
            "CREATE INDEX idx_product_category ON products(category)",
            "CREATE INDEX idx_product_active ON products(is_active)",
        ]

        # Custom SQL constraints
        constraints = """
    __table_args__ = (
        CheckConstraint('price >= 0', name='check_positive_price'),
        CheckConstraint('stock_quantity >= 0', name='check_positive_stock'),
        Index('idx_name_category', 'name', 'category'),
    )"""

        # SQLAlchemy-specific methods
        methods = '''
    @classmethod
    def find_by_category(cls, session, category: str):
        """Find products by category"""
        return session.query(cls).filter(cls.category == category, cls.is_active == True).all()

    def update_stock(self, session, quantity_change: int):
        """Update stock quantity"""
        new_quantity = self.stock_quantity + quantity_change
        if new_quantity < 0:
            raise ValueError("Stock cannot be negative")
        self.stock_quantity = new_quantity
        session.commit()'''

    # Future: Pathway-specific customizations
    class PathwayMeta:
        # This will be used when Pathway generator is implemented
        table_properties = {
            "append_only": True,
            "temporal": True,
            "persistence_mode": "persisted",
        }

        # Pathway-specific transformations
        transformations = '''
@pw.table_transformer
def enrich_product_data(products_table):
    """Add calculated fields for analytics"""
    return products_table.select(
        *pw.this,
        total_value=pw.this.price * pw.this.stock_quantity,
        price_category=pw.if_else(
            pw.this.price < 10, "budget",
            pw.if_else(pw.this.price < 100, "mid_range", "premium")
        )
    )'''

    class Variants:
        # API variants
        create_request = ["name", "price", "category", "stock_quantity"]
        update_request = ["name", "price", "category", "stock_quantity", "is_active"]
        public_response = ["id", "name", "price", "category", "is_active"]

        # Admin variants
        admin_response = [
            "id",
            "name",
            "price",
            "category",
            "stock_quantity",
            "is_active",
            "created_at",
        ]

        # Analytics variants
        inventory_report = ["id", "name", "category", "price", "stock_quantity"]
        sales_analysis = ["name", "category", "price", "created_at"]


def main():
    """Test the target-specific meta classes"""
    from schema_gen.generators.pydantic_generator import PydanticGenerator
    from schema_gen.parsers.schema_parser import SchemaParser

    parser = SchemaParser()
    generator = PydanticGenerator()

    print("=== Testing Basic PydanticMeta Example ===")
    basic_schema = parser.parse_schema(BasicPydanticExample)
    print(f"Basic schema custom code keys: {list(basic_schema.custom_code.keys())}")

    # Should have pydantic key only
    if "pydantic" in basic_schema.custom_code:
        print("✓ PydanticMeta correctly detected")
        pydantic_code = basic_schema.custom_code["pydantic"]
        print(f"  - Has imports: {'imports' in pydantic_code}")
        print(f"  - Has raw_code: {'raw_code' in pydantic_code}")
        print(f"  - Has methods: {'methods' in pydantic_code}")

    print("\n=== Testing Target-Specific Meta Classes ===")
    target_schema = parser.parse_schema(TargetSpecificMetaExample)
    print(
        f"Target-specific schema custom code keys: {list(target_schema.custom_code.keys())}"
    )

    # Should have separate keys for each target
    for target in ["pydantic", "sqlalchemy", "pathway"]:
        if target in target_schema.custom_code:
            print(f"✓ Found {target} custom code")
            code = target_schema.custom_code[target]
            if target == "pydantic":
                print(f"  - Pydantic imports: {'imports' in code}")
                print(f"  - Pydantic validators: {'raw_code' in code}")
                print(f"  - Pydantic methods: {'methods' in code}")
            elif target == "sqlalchemy":
                print(f"  - SQLAlchemy constraints: {'constraints' in code}")
                print(f"  - SQLAlchemy methods: {'methods' in code}")
            elif target == "pathway":
                print(f"  - Pathway transformations: {'transformations' in code}")

    print("\n=== Generating Pydantic Models ===")

    # Test basic model generation
    basic_code = generator.generate_file(basic_schema)
    with open("/tmp/basic_models.py", "w") as f:
        f.write(basic_code)
    print("✓ Basic model generated")

    # Test target-specific model generation
    target_code = generator.generate_file(target_schema)
    with open("/tmp/target_specific_models.py", "w") as f:
        f.write(target_code)
    print("✓ Target-specific model generated")

    # Show that only Pydantic code was used
    print("\n=== Generated Code Sample ===")
    print("First 40 lines of target-specific model:")
    print("=" * 50)
    for i, line in enumerate(target_code.split("\n")[:40], 1):
        print(f"{i:2d}: {line}")

    print("\n=== Future Extensions ===")
    print("When SQLAlchemy generator is implemented, it will use:")
    print("- SQLAlchemyMeta.constraints for table constraints")
    print("- SQLAlchemyMeta.methods for ORM methods")
    print("- SQLAlchemyMeta.indexes for database indexes")
    print()
    print("When Pathway generator is implemented, it will use:")
    print("- PathwayMeta.transformations for data transformations")
    print("- PathwayMeta.table_properties for table configuration")

    print("\n=== Summary ===")
    print("✓ Target-specific Meta classes provide clear separation")
    print("✓ PydanticMeta is used only for Pydantic generation")
    print("✓ SQLAlchemyMeta will be used only for SQLAlchemy generation")
    print("✓ PathwayMeta will be used only for Pathway generation")
    print("✓ No confusion about which code applies to which target")
    print("✓ Clean, explicit, and extensible design")


if __name__ == "__main__":
    main()
