"""Example schema definition"""

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
