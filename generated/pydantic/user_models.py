"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: User
Generated at: 2025-09-07 21:48:29 UTC
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, Field
from pydantic import EmailStr

from datetime import datetime
from typing import Optional, List, Dict, Any, Union


class User(BaseModel):
    """User schema for the application"""
    

    id: int = Field(..., description="Unique identifier")

    name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    email: EmailStr = Field(..., description="User's email address")

    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")

    created_at: datetime = Field(..., description="Account creation timestamp")


"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: User (create_request variant)
Generated at: 2025-09-07 21:48:29 UTC
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, Field
from pydantic import EmailStr

from typing import Optional, List, Dict, Any, Union


class UserCreateRequest(BaseModel):
    """User schema for the application"""
    

    name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    email: EmailStr = Field(..., description="User's email address")

    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")


"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: User (full_response variant)
Generated at: 2025-09-07 21:48:29 UTC
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, Field
from pydantic import EmailStr

from datetime import datetime
from typing import Optional, List, Dict, Any, Union


class UserFullResponse(BaseModel):
    """User schema for the application"""
    

    id: int = Field(..., description="Unique identifier")

    name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    email: EmailStr = Field(..., description="User's email address")

    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")

    created_at: datetime = Field(..., description="Account creation timestamp")


"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: User (public_response variant)
Generated at: 2025-09-07 21:48:29 UTC
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, Field


from datetime import datetime
from typing import Optional, List, Dict, Any, Union


class UserPublicResponse(BaseModel):
    """User schema for the application"""
    

    id: int = Field(..., description="Unique identifier")

    name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")

    created_at: datetime = Field(..., description="Account creation timestamp")


"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: User (update_request variant)
Generated at: 2025-09-07 21:48:29 UTC
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, Field
from pydantic import EmailStr

from typing import Optional, List, Dict, Any, Union


class UserUpdateRequest(BaseModel):
    """User schema for the application"""
    

    name: str = Field(..., min_length=2, max_length=100, description="User's full name")

    email: EmailStr = Field(..., description="User's email address")

    age: Optional[int] = Field(default=None, ge=13, le=120, description="User's age")


