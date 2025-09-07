# Getting Started

This guide will help you get up and running with Schema Gen in just a few minutes.

## Installation

Schema Gen requires Python 3.10 or higher. Install it using pip:

```bash
pip install schema-gen
```

## Your First Schema

Let's create a simple user schema to demonstrate the core concepts.

### 1. Initialize Your Project

```bash
cd your-project
schema-gen init
```

This creates:
- `schemas/` directory for your schema definitions
- `generated/` directory for generated code  
- `.schema-gen.config.py` configuration file
- `schemas/user.py` example schema

### 2. Examine the Example Schema

Look at the generated `schemas/user.py`:

```python
from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime

@Schema
class User:
    """User schema for the application"""
    
    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Unique identifier"
    )
    
    name: str = Field(
        max_length=100,
        min_length=2,
        description="User's full name"
    )
    
    email: str = Field(
        unique=True,
        format="email",
        description="User's email address"
    )
    
    age: Optional[int] = Field(
        default=None,
        min_value=13,
        max_value=120,
        description="User's age"
    )
    
    created_at: datetime = Field(
        auto_now_add=True,
        description="Account creation timestamp"
    )
    
    class Variants:
        create_request = ['name', 'email', 'age']
        update_request = ['name', 'email', 'age'] 
        public_response = ['id', 'name', 'age', 'created_at']
        full_response = ['id', 'name', 'email', 'age', 'created_at']
```

### 3. Generate Your Models

```bash
schema-gen generate
```

This creates:
- `generated/pydantic/user_models.py` - Complete Pydantic models
- `generated/pydantic/__init__.py` - Package initialization

### 4. Examine the Generated Models

Look at `generated/pydantic/user_models.py`:

```python
"""AUTO-GENERATED FILE - DO NOT EDIT

Generated from: schemas/user.py
Generated on: 2024-01-15 10:30:00
"""

from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional

class User(BaseModel):
    """User schema for the application"""
    
    id: int = Field(..., description="Unique identifier")
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")  
    email: EmailStr = Field(..., description="User's email address")
    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")
    created_at: datetime = Field(..., description="Account creation timestamp")
    
    class Config:
        from_attributes = True

class UserCreateRequest(BaseModel):
    """User schema for the application - create_request variant"""
    
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address") 
    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")
    
    class Config:
        from_attributes = True

# ... additional variant models
```

### 5. Use in Your Application

Now you can import and use the generated models:

```python
from fastapi import FastAPI
from generated.pydantic.user_models import User, UserCreateRequest, UserPublicResponse

app = FastAPI()

@app.post("/users", response_model=UserPublicResponse)
async def create_user(user_data: UserCreateRequest):
    # Your logic here
    return UserPublicResponse(
        id=1,
        name=user_data.name,
        age=user_data.age,
        created_at=datetime.now()
    )
```

## Key Concepts

### Schemas
A schema is a Python class decorated with `@Schema` that defines the structure of your data. It includes:
- Field definitions with types and constraints
- Documentation strings
- Variant definitions for different use cases

### Fields
Fields are defined using the `Field()` function, which accepts:
- **Validation constraints** - `min_length`, `max_length`, `min_value`, `max_value`
- **Format specifications** - `format="email"`, `regex` patterns
- **Database properties** - `primary_key`, `unique`, `index`
- **Documentation** - `description` for generated docs
- **Target-specific options** - `pydantic={}`, `sqlalchemy={}`

### Variants
Variants allow you to create different views of the same schema:
- **API variants** - Different models for requests vs responses
- **Permission variants** - Public vs admin views
- **Use case variants** - Creation, update, listing, etc.

## Development Workflow

### File Watching
For active development, use the watch mode:

```bash
schema-gen watch
```

This automatically regenerates models when you modify schemas.

### Validation
Check that generated files are up-to-date:

```bash
schema-gen validate
```

### Pre-commit Integration
Set up automatic generation in your git workflow:

```bash
schema-gen install-hooks
```

This ensures generated files stay in sync with schema changes.

## Next Steps

- **[Schema Format Reference](schema-format.md)** - Complete field types and constraints
- **[CLI Reference](cli-reference.md)** - All command-line tools
- **[Configuration](configuration.md)** - Project configuration options
- **[Examples](examples.md)** - Real-world usage patterns