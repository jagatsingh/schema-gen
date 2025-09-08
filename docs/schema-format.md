# Schema Gen Input Format Specification

This document provides a complete specification of the Schema Gen input format for defining schemas in Python.

## Overview

Schema Gen uses Python classes with decorators and type annotations as the schema definition language. This provides full IDE support, type checking, and familiar syntax for Python developers.

## Basic Structure

```python
from schema_gen import Schema, Field
from typing import Optional, List, Union, Literal
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID


@Schema
class MySchema:
    """Schema description (optional)"""

    # Field definitions
    field_name: field_type = Field(...)

    # Variant definitions (optional)
    class Variants:
        variant_name = ["field1", "field2", ...]
```

## Field Types

### Basic Types

| Python Type | USR Type | Pydantic Output | SQLAlchemy Output | Description |
|-------------|----------|-----------------|-------------------|-------------|
| `str` | STRING | `str` | `String` | Text string |
| `int` | INTEGER | `int` | `Integer` | Integer number |
| `float` | FLOAT | `float` | `Float` | Floating point |
| `bool` | BOOLEAN | `bool` | `Boolean` | Boolean value |
| `bytes` | BYTES | `bytes` | `LargeBinary` | Binary data |

### Date and Time Types

| Python Type | USR Type | Pydantic Output | Description |
|-------------|----------|-----------------|-------------|
| `datetime` | DATETIME | `datetime` | Date and time |
| `date` | DATE | `date` | Date only |
| `time` | TIME | `time` | Time only |

### Special Types

| Python Type | USR Type | Pydantic Output | Description |
|-------------|----------|-----------------|-------------|
| `UUID` | UUID | `UUID` | UUID identifier |
| `Decimal` | DECIMAL | `Decimal` | Precise decimal |
| `dict` | DICT | `Dict[str, Any]` | Dictionary/JSON |

### Container Types

```python
# List types
tags: List[str] = Field()  # List of strings
scores: List[int] = Field()  # List of integers
nested: List["OtherSchema"] = Field()  # List of nested schemas

# Dictionary types
metadata: Dict[str, Any] = Field()  # String-keyed dictionary
mapping: Dict[str, int] = Field()  # Typed dictionary

# Optional types
age: Optional[int] = Field()  # Nullable integer
name: Optional[str] = Field(default=None)  # With explicit default

# Union types
value: Union[str, int] = Field()  # String or integer
result: Union[str, int, float] = Field()  # Multiple types

# Literal types
status: Literal["active", "inactive"] = Field()  # Enumerated values
```

## Field Configuration

The `Field()` function accepts numerous parameters to configure field behavior:

### Basic Field Parameters

```python
Field(
    # Default values
    default=None,  # Static default value
    default_factory=list,  # Factory function for default
    # Documentation
    description="Field description",  # Human-readable description
)
```

### Validation Constraints

```python
Field(
    # String constraints
    min_length=2,  # Minimum string length
    max_length=100,  # Maximum string length
    regex=r"^[A-Za-z]+$",  # Regular expression pattern
    # Numeric constraints
    min_value=0,  # Minimum numeric value (inclusive)
    max_value=150,  # Maximum numeric value (inclusive)
    # Format validation
    format="email",  # Built-in format validation
    # Supported formats: email, uri, uuid, ipv4, ipv6, hostname
)
```

### Database Properties

```python
Field(
    # Primary key configuration
    primary_key=True,  # Mark as primary key
    auto_increment=True,  # Auto-incrementing primary key
    # Index and uniqueness
    unique=True,  # Unique constraint
    index=True,  # Database index
    # Foreign key relationships
    foreign_key="users.id",  # Reference to another table
    # Automatic timestamps
    auto_now_add=True,  # Set on creation (created_at)
    auto_now=True,  # Update on every save (updated_at)
)
```

### Relationship Configuration

```python
Field(
    # Relationship types
    relationship="one_to_many",  # Types: one_to_many, many_to_one, many_to_many
    # Relationship metadata
    back_populates="related_field",  # Bidirectional relationship
    cascade="all, delete-orphan",  # SQLAlchemy cascade options
    through_table="join_table",  # Many-to-many join table
)
```

### Generation Control

```python
Field(
    # Exclude from specific variants
    exclude_from=["create_request", "public_api"],
    # Include only in specific variants
    include_only=["admin_view", "internal_api"],
)
```

### Target-Specific Configuration

```python
Field(
    # Pydantic-specific options
    pydantic={
        "alias": "fieldName",  # JSON field name
        "example": "sample_value",  # OpenAPI example
        "deprecated": True,  # Mark as deprecated
        "exclude": True,  # Exclude from serialization
    },
    # SQLAlchemy-specific options
    sqlalchemy={
        "column_name": "field_name",  # Database column name
        "nullable": False,  # Override nullable setting
        "server_default": "''",  # Database default value
        "comment": "Field comment",  # Column comment
    },
    # Pathway-specific options
    pathway={
        "column_type": "pw.Column[str]",  # Explicit column type
        "optional": False,  # Override optional setting
    },
    # Additional metadata
    custom_metadata={
        "ui_component": "textarea",  # Custom metadata for other tools
        "validation_group": "user",  # Grouping for validation
    },
)
```

## Complete Field Examples

### User Information Fields

```python
@Schema
class User:
    # Primary key with auto-increment
    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Unique user identifier",
        exclude_from=["create_request", "update_request"],
    )

    # Username with validation
    username: str = Field(
        min_length=3,
        max_length=30,
        regex=r"^[a-zA-Z0-9_]+$",
        unique=True,
        description="Unique username",
        pydantic={"example": "john_doe"},
    )

    # Email with format validation
    email: str = Field(
        format="email",
        unique=True,
        index=True,
        description="User email address",
        pydantic={"example": "john@example.com"},
    )

    # Password with special handling
    password: str = Field(
        min_length=8,
        description="User password",
        exclude_from=["response", "public_api"],
        pydantic={"write_only": True},
    )

    # Optional profile information
    full_name: Optional[str] = Field(
        default=None, max_length=100, description="User's full name"
    )

    # Age with constraints
    age: Optional[int] = Field(
        default=None, min_value=13, max_value=120, description="User's age"
    )

    # Profile picture URL
    avatar_url: Optional[str] = Field(
        default=None, format="uri", max_length=500, description="Profile picture URL"
    )

    # User status with enumeration
    status: Literal["active", "inactive", "suspended"] = Field(
        default="active", description="User account status"
    )

    # JSON metadata
    preferences: Dict[str, Any] = Field(
        default_factory=dict, description="User preferences as JSON"
    )

    # Automatic timestamps
    created_at: datetime = Field(
        auto_now_add=True,
        description="Account creation timestamp",
        exclude_from=["create_request", "update_request"],
    )

    updated_at: datetime = Field(
        auto_now=True,
        description="Last update timestamp",
        exclude_from=["create_request"],
    )
```

### E-commerce Product Schema

```python
@Schema
class Product:
    # Product identification
    id: UUID = Field(
        primary_key=True, default_factory=uuid4, description="Product UUID"
    )

    # Product details
    name: str = Field(min_length=1, max_length=200, description="Product name")

    description: Optional[str] = Field(
        default=None, max_length=5000, description="Product description"
    )

    # SEO-friendly URL slug
    slug: str = Field(
        unique=True,
        regex=r"^[a-z0-9-]+$",
        max_length=100,
        description="URL-friendly product identifier",
    )

    # Pricing with precise decimal
    price: Decimal = Field(
        min_value=0,
        decimal_places=2,
        max_digits=10,
        description="Product price in dollars",
    )

    # Inventory
    stock_quantity: int = Field(
        min_value=0, default=0, description="Available stock quantity"
    )

    # Product categorization
    category_id: int = Field(
        foreign_key="categories.id", description="Product category reference"
    )

    tags: List[str] = Field(
        default_factory=list, max_items=10, description="Product tags"
    )

    # Product images
    images: List[str] = Field(
        default_factory=list, max_items=5, description="Product image URLs"
    )

    # Product specifications
    specifications: Dict[str, str] = Field(
        default_factory=dict, description="Product specifications as key-value pairs"
    )

    # Publication status
    is_published: bool = Field(
        default=False, description="Whether product is published"
    )

    # Relationships
    category: "Category" = Field(relationship="many_to_one", back_populates="products")

    reviews: List["Review"] = Field(
        relationship="one_to_many",
        back_populates="product",
        exclude_from=["create_request", "list_response"],
    )
```

## Schema Variants

Variants allow you to define different views of your schema for different use cases:

```python
@Schema
class User:
    id: int = Field(primary_key=True)
    username: str = Field()
    email: str = Field(format="email")
    password: str = Field()
    full_name: Optional[str] = Field(default=None)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(auto_now_add=True)

    class Variants:
        # API request models (exclude server-generated fields)
        create_request = ["username", "email", "password", "full_name"]
        login_request = ["username", "password"]
        update_profile = ["email", "full_name"]

        # API response models (exclude sensitive fields)
        public_profile = ["id", "username", "full_name"]
        private_profile = ["id", "username", "email", "full_name", "created_at"]
        admin_view = ["id", "username", "email", "full_name", "is_admin", "created_at"]

        # Data processing schemas
        analytics_export = ["id", "created_at", "is_admin"]
        email_template = ["username", "email", "full_name"]

        # Database model (all fields)
        database_model = "__all__"  # Special value for all fields
```

This generates separate model classes:
- `UserCreateRequest`
- `UserLoginRequest`
- `UserUpdateProfile`
- `UserPublicProfile`
- `UserPrivateProfile`
- `UserAdminView`
- `UserAnalyticsExport`
- `UserEmailTemplate`
- `User` (base model with all fields)

## Custom Code Injection

Schema Gen supports injecting custom code into generated models for complex scenarios like custom validators, methods, and other advanced features.

### Target-Specific Meta Classes for Custom Code

```python
from schema_gen import Schema, Field
from datetime import datetime
import math


@Schema
class AdvancedModel:
    """Model with custom validators and methods"""

    # Regular fields
    price: float = Field(description="Product price")
    quantity: int = Field(description="Quantity in stock")
    volatility: float = Field(description="Price volatility")

    class PydanticMeta:
        # Custom imports needed for validators/methods
        imports = [
            "import math",
            "from pydantic import field_validator",
            "from decimal import Decimal",
        ]

        # Custom validators (Pydantic-specific)
        raw_code = '''
    @field_validator("price", "volatility", mode="before")
    def validate_numeric_fields(cls, value) -> float:
        """Handle None, string, NaN, and infinite values"""
        if value is None:
            return 0.0
        if isinstance(value, str):
            if value.lower() in ["inf", "-inf", "nan", "none", "n/a", "na", ""]:
                return 0.0
            try:
                value = float(value)
            except (ValueError, TypeError):
                return 0.0
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return float(value)
        return 0.0'''

        # Custom instance methods
        methods = '''
    def calculate_total_value(self) -> float:
        """Calculate total monetary value"""
        return self.price * self.quantity

    def is_high_volatility(self) -> bool:
        """Check if volatility is above threshold"""
        return self.volatility > 0.3

    def get_risk_metrics(self) -> dict:
        """Get risk assessment metrics"""
        return {
            "total_value": self.calculate_total_value(),
            "high_volatility": self.is_high_volatility(),
            "risk_score": self.volatility * self.price
        }'''
```

### Generated Output

The above schema generates a Pydantic model like this:

```python
class AdvancedModel(BaseModel):
    """Model with custom validators and methods"""

    price: float = Field(..., description="Product price")
    quantity: int = Field(..., description="Quantity in stock")
    volatility: float = Field(..., description="Price volatility")

    # Custom validators
    @field_validator("price", "volatility", mode="before")
    def validate_numeric_fields(cls, value) -> float:
        """Handle None, string, NaN, and infinite values"""
        if value is None:
            return 0.0
        # ... validation logic

    # Custom methods
    def calculate_total_value(self) -> float:
        """Calculate total monetary value"""
        return self.price * self.quantity

    def is_high_volatility(self) -> bool:
        """Check if volatility is above threshold"""
        return self.volatility > 0.3
```

### Target-Specific Meta Classes

Schema Gen supports different meta classes for different code generation targets:

| Meta Class | Target | Description |
|------------|--------|-------------|
| `PydanticMeta` | Pydantic | Custom validators, methods, and imports for Pydantic models |
| `SQLAlchemyMeta` | SQLAlchemy | Custom constraints, methods, and table configuration |
| `PathwayMeta` | Pathway | Custom transformations and table properties |

### PydanticMeta Options

| Option | Description | Use Case |
|--------|-------------|----------|
| `imports` | List of import statements | Add dependencies for custom code |
| `raw_code` | Raw Python code (validators, class methods) | Complex validation logic |
| `methods` | Instance methods | Business logic methods |
| `validators` | Validation functions | Field-specific validation |

### SQLAlchemyMeta Options (Future)

| Option | Description | Use Case |
|--------|-------------|----------|
| `table_name` | Custom table name | Override default table naming |
| `indexes` | List of custom indexes | Database performance optimization |
| `constraints` | Custom table constraints | Data integrity rules |
| `methods` | ORM methods | Database-specific functionality |

### PathwayMeta Options (Future)

| Option | Description | Use Case |
|--------|-------------|----------|
| `table_properties` | Pathway table configuration | Streaming, persistence settings |
| `transformations` | Data transformation functions | Real-time data processing |
| `methods` | Pathway-specific methods | Stream processing logic |

### Important Notes

1. **Base Model Only**: Custom code is injected only into the base model class, not variant models
2. **Target Specific**: Each Meta class is used only by its corresponding generator
3. **Proper Indentation**: Code should be properly indented for class methods (4 spaces)
4. **Import Management**: List required imports in the `imports` array
5. **Clear Separation**: No confusion about which code applies to which target

### Real-World Example: Financial Data Model

```python
@Schema
class OptionQuote:
    """Options market data with custom validation and calculations"""

    symbol: str = Field(description="Option symbol")
    strike_price: float = Field(description="Strike price")
    last_price: float = Field(description="Last traded price")
    bid: float = Field(description="Bid price")
    ask: float = Field(description="Ask price")

    # Greeks
    delta: float = Field(description="Delta value")
    gamma: float = Field(description="Gamma value")
    theta: float = Field(description="Theta value")
    vega: float = Field(description="Vega value")

    # Market data
    volume: int = Field(description="Trading volume")
    open_interest: int = Field(description="Open interest")
    implied_volatility: float = Field(description="Implied volatility")

    class PydanticMeta:
        imports = ["import math", "from pydantic import field_validator"]

        raw_code = '''
    @field_validator(
        "delta", "gamma", "theta", "vega", "implied_volatility",
        mode="before"
    )
    def sanitize_greeks(cls, value) -> float:
        """Clean and validate options Greeks data"""
        if value is None:
            return 0.0
        if isinstance(value, str):
            if value.lower() in ["inf", "-inf", "nan", "n/a", ""]:
                return 0.0
            try:
                value = float(value)
            except (ValueError, TypeError):
                return 0.0
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return 0.0
            return float(value)
        return 0.0'''

        methods = '''
    def calculate_bid_ask_spread(self) -> float:
        """Calculate bid-ask spread percentage"""
        if self.last_price == 0:
            return 0.0
        return abs(self.ask - self.bid) / self.last_price

    def is_liquid(self, min_volume: int = 100) -> bool:
        """Check if option has sufficient liquidity"""
        return self.volume >= min_volume and self.open_interest > 0

    def get_greeks_summary(self) -> dict:
        """Get summary of all Greeks"""
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega
        }

    def risk_assessment(self) -> str:
        """Simple risk assessment based on Greeks"""
        if abs(self.delta) > 0.7:
            return "high_delta_risk"
        elif self.implied_volatility > 0.5:
            return "high_volatility"
        elif not self.is_liquid():
            return "liquidity_risk"
        return "normal"'''

    class Variants:
        # Basic quote info for display
        quote_basic = ["symbol", "last_price", "bid", "ask", "volume"]

        # Greeks only for analysis
        greeks_only = ["symbol", "delta", "gamma", "theta", "vega"]

        # Full data for detailed analysis
        full_analysis = [
            "symbol",
            "strike_price",
            "last_price",
            "bid",
            "ask",
            "delta",
            "gamma",
            "theta",
            "vega",
            "implied_volatility",
            "volume",
            "open_interest",
        ]
```

This generates multiple models:
- `OptionQuote` (base model with all fields and custom methods)
- `OptionQuoteBasic` (variant with quote fields only, no custom code)
- `OptionQuoteGreeksOnly` (variant with Greeks only, no custom code)
- `OptionQuoteFullAnalysis` (variant with analysis fields, no custom code)

## Advanced Features

### Conditional Fields

```python
@Schema
class ConditionalSchema:
    type: Literal["user", "admin"] = Field()

    # Fields that exist based on conditions
    user_data: Optional[str] = Field(
        default=None,
        include_only=["user_variant"],
        description="Only included in user variant",
    )

    admin_data: Optional[str] = Field(
        default=None,
        include_only=["admin_variant"],
        description="Only included in admin variant",
    )
```

### Inheritance and Composition

```python
@Schema
class BaseEntity:
    """Base schema with common fields"""

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    created_at: datetime = Field(auto_now_add=True)
    updated_at: datetime = Field(auto_now=True)


@Schema
class User(BaseEntity):
    """User inherits base fields"""

    username: str = Field(unique=True)
    email: str = Field(format="email")
```

### Complex Relationships

```python
@Schema
class User:
    id: int = Field(primary_key=True)
    posts: List["Post"] = Field(relationship="one_to_many", back_populates="author")

    roles: List["Role"] = Field(relationship="many_to_many", through_table="user_roles")


@Schema
class Post:
    id: int = Field(primary_key=True)
    author_id: int = Field(foreign_key="users.id")
    author: "User" = Field(relationship="many_to_one", back_populates="posts")


@Schema
class Role:
    id: int = Field(primary_key=True)
    users: List["User"] = Field(relationship="many_to_many", back_populates="roles")
```

## Best Practices

### 1. Use Descriptive Names and Documentation

```python
@Schema
class UserAccount:
    """User account information for the application

    This schema represents a user account with authentication
    and profile information.
    """

    username: str = Field(
        min_length=3,
        max_length=30,
        regex=r"^[a-zA-Z0-9_]+$",
        description="Unique username for login, alphanumeric and underscores only",
    )
```

### 2. Use Appropriate Constraints

```python
# Be specific with validation
email: str = Field(format="email", max_length=254)  # RFC 5321 limit
age: int = Field(min_value=0, max_value=150)  # Reasonable age range
price: Decimal = Field(min_value=0, decimal_places=2, max_digits=10)
```

### 3. Design Variants for Different Use Cases

```python
class Variants:
    # Clear, purpose-driven variant names
    create_request = ["username", "email", "password"]
    update_profile = ["email", "full_name", "avatar_url"]
    public_api = ["id", "username", "avatar_url"]
    admin_view = "__all__"  # Admins see everything
```

### 4. Use Appropriate Default Values

```python
# Use factories for mutable defaults
tags: List[str] = Field(default_factory=list)
metadata: Dict[str, Any] = Field(default_factory=dict)

# Use static defaults for immutable values
status: str = Field(default="active")
is_verified: bool = Field(default=False)
```

### 5. Organize Related Fields

```python
@Schema
class User:
    # Identity fields
    id: UUID = Field(primary_key=True)
    username: str = Field(unique=True)
    email: str = Field(format="email", unique=True)

    # Profile fields
    full_name: Optional[str] = Field(default=None)
    bio: Optional[str] = Field(default=None)
    avatar_url: Optional[str] = Field(default=None)

    # System fields
    created_at: datetime = Field(auto_now_add=True)
    updated_at: datetime = Field(auto_now=True)
    is_active: bool = Field(default=True)
```

This specification provides a complete reference for defining schemas in Schema Gen. The format is designed to be both powerful and intuitive, leveraging Python's type system while providing extensive customization options for different target formats.
