#!/usr/bin/env python3
"""
Example demonstrating custom code injection in Schema Gen

This example shows how to use the Meta class to inject custom validators,
methods, and imports into generated Pydantic models.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime

from schema_gen import Field, Schema


@Schema
class FinancialInstrument:
    """Financial instrument with custom validation and business logic"""

    # Basic instrument info
    symbol: str = Field(min_length=1, max_length=10, description="Trading symbol")

    name: str = Field(
        min_length=1, max_length=100, description="Full name of the instrument"
    )

    # Price and market data
    current_price: float = Field(min_value=0, description="Current market price")

    # Volatile fields that might contain bad data
    volatility: float = Field(description="Price volatility (can be messy data)")
    beta: float = Field(description="Beta coefficient (can be messy data)")
    pe_ratio: float | None = Field(default=None, description="P/E ratio")

    # Market metrics
    volume: int = Field(min_value=0, default=0, description="Trading volume")

    market_cap: float | None = Field(
        default=None, min_value=0, description="Market capitalization"
    )

    # Timestamps
    last_updated: datetime = Field(
        auto_now=True, description="When data was last updated"
    )

    class PydanticMeta:
        # Custom imports needed for validators and methods
        imports = [
            "import math",
            "from pydantic import field_validator",
            "from decimal import Decimal, InvalidOperation",
        ]

        # Custom field validators
        raw_code = '''
    @field_validator("volatility", "beta", "pe_ratio", mode="before")
    def clean_numeric_fields(cls, value) -> float:
        """
        Clean numeric fields that might contain NaN, infinity, or string values
        from market data feeds.
        """
        # Handle None values
        if value is None:
            return 0.0

        # Handle string values from data feeds
        if isinstance(value, str):
            value_clean = value.lower().strip()
            # Common representations of invalid/missing data
            if value_clean in ["nan", "inf", "-inf", "n/a", "na", "null", "", "--"]:
                return 0.0
            # Try to parse as number
            try:
                value = float(value)
            except (ValueError, TypeError):
                return 0.0

        # Handle numeric values
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return float(value)

        return 0.0

    @field_validator("current_price", mode="after")
    def validate_price(cls, value):
        """Ensure price is reasonable"""
        if value <= 0:
            raise ValueError("Price must be positive")
        if value > 100000:  # Sanity check
            raise ValueError("Price seems unreasonably high")
        return value'''

        # Custom instance methods for business logic
        methods = '''
    def calculate_position_value(self, shares: int) -> float:
        """Calculate total value of a position"""
        return self.current_price * shares

    def is_high_volatility(self, threshold: float = 0.3) -> bool:
        """Check if instrument has high volatility"""
        return self.volatility > threshold

    def get_risk_category(self) -> str:
        """Categorize risk level based on various metrics"""
        if self.volatility > 0.5 or self.beta > 1.5:
            return "high_risk"
        elif self.volatility > 0.2 or self.beta > 1.0:
            return "medium_risk"
        else:
            return "low_risk"

    def is_actively_traded(self, min_volume: int = 100000) -> bool:
        """Check if instrument is actively traded"""
        return self.volume >= min_volume

    def get_market_metrics(self) -> dict:
        """Get comprehensive market metrics"""
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "volatility": self.volatility,
            "beta": self.beta,
            "pe_ratio": self.pe_ratio,
            "volume": self.volume,
            "market_cap": self.market_cap,
            "risk_category": self.get_risk_category(),
            "high_volatility": self.is_high_volatility(),
            "actively_traded": self.is_actively_traded()
        }

    def format_for_display(self) -> str:
        """Format instrument for display"""
        return f"{self.symbol} ({self.name}) - ${self.current_price:.2f}"'''

    class Variants:
        # Trading interface - essential info for traders
        trading_view = ["symbol", "name", "current_price", "volume", "last_updated"]

        # Risk analysis - focus on risk metrics
        risk_analysis = ["symbol", "current_price", "volatility", "beta", "volume"]

        # Portfolio summary - compact info for portfolio views
        portfolio_summary = ["symbol", "name", "current_price", "market_cap"]

        # Full analysis - comprehensive data
        full_analysis = [
            "symbol",
            "name",
            "current_price",
            "volatility",
            "beta",
            "pe_ratio",
            "volume",
            "market_cap",
            "last_updated",
        ]


def main():
    """Demonstrate the custom validation and methods"""
    from schema_gen.generators.pydantic_generator import PydanticGenerator
    from schema_gen.parsers.schema_parser import SchemaParser

    # Parse the schema
    parser = SchemaParser()
    usr_schema = parser.parse_schema(FinancialInstrument)

    print("=== Schema Information ===")
    print(f"Schema: {usr_schema.name}")
    print(f"Fields: {len(usr_schema.fields)}")
    print(f"Variants: {list(usr_schema.variants.keys())}")
    print(f"Custom code sections: {list(usr_schema.custom_code.keys())}")

    # Generate Pydantic models
    generator = PydanticGenerator()
    generated_code = generator.generate_file(usr_schema)

    # Save generated code
    output_file = "/tmp/financial_models.py"
    with open(output_file, "w") as f:
        f.write(generated_code)

    print("\n=== Generated Code ===")
    print(f"Generated models saved to: {output_file}")
    print("\nFirst 30 lines of generated code:")
    print("=" * 50)
    for i, line in enumerate(generated_code.split("\n")[:30], 1):
        print(f"{i:2d}: {line}")

    print("\n=== Testing Generated Models ===")

    # Test with sample data (some with problematic values)
    test_data = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "current_price": 150.25,
        "volatility": "nan",  # This should be cleaned to 0.0
        "beta": float("inf"),  # This should be cleaned to 0.0
        "pe_ratio": "25.5",  # String that should be converted
        "volume": 1500000,
        "market_cap": 2500000000.0,
        "last_updated": datetime.now(),
    }

    print("Test data contains problematic values:")
    print(f"  volatility: {test_data['volatility']} (should be cleaned)")
    print(f"  beta: {test_data['beta']} (should be cleaned)")
    print(f"  pe_ratio: {test_data['pe_ratio']} (string that should convert)")

    # Try to import and use the generated models
    try:
        # Add the temp directory to path so we can import
        sys.path.insert(0, "/tmp")

        # Import the generated models (rename to avoid conflict)
        from financial_models import FinancialInstrument as GeneratedFinancialInstrument
        from financial_models import FinancialInstrumentTradingView

        # Create instance with custom validation
        instrument = GeneratedFinancialInstrument(**test_data)

        print("\n✓ Model created successfully!")
        print(f"  Cleaned volatility: {instrument.volatility}")
        print(f"  Cleaned beta: {instrument.beta}")
        print(f"  Converted pe_ratio: {instrument.pe_ratio}")

        # Test custom methods
        print("\n=== Custom Methods ===")
        print(
            f"Position value (1000 shares): ${instrument.calculate_position_value(1000):,.2f}"
        )
        print(f"High volatility: {instrument.is_high_volatility()}")
        print(f"Risk category: {instrument.get_risk_category()}")
        print(f"Actively traded: {instrument.is_actively_traded()}")
        print(f"Display format: {instrument.format_for_display()}")

        # Test variant model (should not have custom methods)
        trading_view = FinancialInstrumentTradingView(
            symbol=instrument.symbol,
            name=instrument.name,
            current_price=instrument.current_price,
            volume=instrument.volume,
            last_updated=instrument.last_updated,
        )

        print("\n=== Variant Model ===")
        print(f"✓ Trading view created: {trading_view.symbol}")
        print(
            f"Has custom methods: {hasattr(trading_view, 'calculate_position_value')}"
        )
        print(f"Has custom validators: {hasattr(trading_view, 'clean_numeric_fields')}")

    except ImportError as e:
        print(f"\n✗ Could not import generated models: {e}")
        print("This is expected if pydantic is not available in the environment")
    except Exception as e:
        print(f"\n✗ Error testing models: {e}")

    print("\n=== Summary ===")
    print("✓ Schema with custom code defined")
    print("✓ Pydantic models generated with custom validators and methods")
    print("✓ Custom code only in base model, variants are clean")
    print("✓ Custom validators handle messy real-world data")
    print("✓ Custom methods provide business logic")


if __name__ == "__main__":
    main()
