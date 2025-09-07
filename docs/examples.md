# Examples

This page provides real-world examples of using Schema Gen in different scenarios.

## FastAPI Application

Complete example of a FastAPI application using Schema Gen for consistent models.

### Project Structure
```
my-api/
├── schemas/
│   ├── user.py
│   ├── product.py
│   └── order.py
├── generated/
│   └── pydantic/
│       ├── user_models.py
│       ├── product_models.py
│       └── order_models.py
├── app/
│   ├── main.py
│   ├── routers/
│   └── database.py
└── .schema-gen.config.py
```

### User Schema

```python
# schemas/user.py
from schema_gen import Schema, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

@Schema
class User:
    """User account schema"""
    
    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Unique user identifier"
    )
    
    username: str = Field(
        min_length=3,
        max_length=30,
        regex=r'^[a-zA-Z0-9_]+$',
        unique=True,
        description="Unique username"
    )
    
    email: str = Field(
        format="email",
        unique=True,
        description="User email address"
    )
    
    password_hash: str = Field(
        min_length=8,
        description="Hashed password",
        exclude_from=['public_response', 'admin_response']
    )
    
    first_name: str = Field(
        max_length=50,
        description="User's first name"
    )
    
    last_name: str = Field(
        max_length=50,
        description="User's last name"
    )
    
    is_active: bool = Field(
        default=True,
        description="Whether the account is active"
    )
    
    is_admin: bool = Field(
        default=False,
        description="Whether the user has admin privileges",
        exclude_from=['public_response']
    )
    
    created_at: datetime = Field(
        auto_now_add=True,
        description="Account creation timestamp"
    )
    
    updated_at: datetime = Field(
        auto_now=True,
        description="Last update timestamp"
    )
    
    class Variants:
        # Registration and authentication
        register_request = ['username', 'email', 'password_hash', 'first_name', 'last_name']
        login_request = ['username', 'password_hash']
        
        # User management
        update_profile = ['email', 'first_name', 'last_name']
        change_password = ['password_hash']
        
        # API responses
        public_response = ['id', 'username', 'first_name', 'last_name', 'created_at']
        private_response = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'created_at', 'updated_at']
        admin_response = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_admin', 'created_at', 'updated_at']
```

### Product Schema

```python
# schemas/product.py
from schema_gen import Schema, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

@Schema
class Product:
    """Product catalog schema"""
    
    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Product ID"
    )
    
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Product name"
    )
    
    slug: str = Field(
        unique=True,
        regex=r'^[a-z0-9-]+$',
        max_length=100,
        description="URL-friendly product identifier"
    )
    
    description: Optional[str] = Field(
        default=None,
        max_length=5000,
        description="Product description"
    )
    
    price: Decimal = Field(
        min_value=0,
        max_digits=10,
        decimal_places=2,
        description="Product price"
    )
    
    stock_quantity: int = Field(
        min_value=0,
        default=0,
        description="Available stock"
    )
    
    category_id: int = Field(
        foreign_key="categories.id",
        description="Product category"
    )
    
    tags: List[str] = Field(
        default_factory=list,
        max_items=10,
        description="Product tags"
    )
    
    is_published: bool = Field(
        default=False,
        description="Whether product is published"
    )
    
    created_at: datetime = Field(auto_now_add=True)
    updated_at: datetime = Field(auto_now=True)
    
    class Variants:
        # Admin management
        create_request = ['name', 'slug', 'description', 'price', 'stock_quantity', 'category_id', 'tags']
        update_request = ['name', 'description', 'price', 'stock_quantity', 'category_id', 'tags', 'is_published']
        
        # Public API
        list_response = ['id', 'name', 'slug', 'price', 'stock_quantity', 'tags']
        detail_response = ['id', 'name', 'slug', 'description', 'price', 'stock_quantity', 'tags', 'category_id']
        
        # Admin views
        admin_list = ['id', 'name', 'slug', 'price', 'stock_quantity', 'is_published', 'created_at', 'updated_at']
        admin_detail = '__all__'
```

### FastAPI Application

```python
# app/main.py
from fastapi import FastAPI, HTTPException, Depends
from generated.pydantic.user_models import (
    User, UserRegisterRequest, UserUpdateProfile, 
    UserPublicResponse, UserPrivateResponse, UserAdminResponse
)
from generated.pydantic.product_models import (
    Product, ProductCreateRequest, ProductUpdateRequest,
    ProductListResponse, ProductDetailResponse, ProductAdminDetail
)

app = FastAPI(title="My API", version="1.0.0")

# User endpoints
@app.post("/register", response_model=UserPublicResponse)
async def register_user(user_data: UserRegisterRequest):
    """Register a new user"""
    # Hash password, save to database, etc.
    return UserPublicResponse(
        id=1,
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        created_at=datetime.now()
    )

@app.get("/users/{user_id}", response_model=UserPrivateResponse)
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    """Get user profile"""
    # Authorization checks, database query, etc.
    return UserPrivateResponse(...)

@app.put("/users/profile", response_model=UserPrivateResponse)
async def update_profile(
    profile_data: UserUpdateProfile,
    current_user: User = Depends(get_current_user)
):
    """Update user profile"""
    # Update database, etc.
    return UserPrivateResponse(...)

# Product endpoints
@app.post("/products", response_model=ProductDetailResponse)
async def create_product(
    product_data: ProductCreateRequest,
    current_user: User = Depends(get_current_admin)
):
    """Create a new product"""
    return ProductDetailResponse(...)

@app.get("/products", response_model=List[ProductListResponse])
async def list_products():
    """List all published products"""
    return [ProductListResponse(...)]

@app.get("/products/{product_id}", response_model=ProductDetailResponse)
async def get_product(product_id: int):
    """Get product details"""
    return ProductDetailResponse(...)

# Admin endpoints  
@app.get("/admin/products", response_model=List[ProductAdminDetail])
async def admin_list_products(current_user: User = Depends(get_current_admin)):
    """Admin view of all products"""
    return [ProductAdminDetail(...)]
```

## Data Processing Pipeline

Example using Schema Gen for data processing and analytics.

### Analytics Schema

```python
# schemas/analytics.py
from schema_gen import Schema, Field
from typing import Optional, Dict, Any
from datetime import datetime, date

@Schema
class UserEvent:
    """User behavior tracking event"""
    
    event_id: str = Field(
        primary_key=True,
        description="Unique event identifier"
    )
    
    user_id: Optional[int] = Field(
        default=None,
        foreign_key="users.id",
        description="User who triggered the event"
    )
    
    session_id: str = Field(
        max_length=100,
        description="User session identifier"
    )
    
    event_type: str = Field(
        max_length=50,
        description="Type of event (page_view, click, purchase, etc.)"
    )
    
    event_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific data"
    )
    
    url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="URL where event occurred"
    )
    
    user_agent: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Browser user agent"
    )
    
    ip_address: Optional[str] = Field(
        default=None,
        format="ipv4",
        description="User IP address"
    )
    
    timestamp: datetime = Field(
        auto_now_add=True,
        description="When the event occurred"
    )
    
    class Variants:
        # Data ingestion
        ingestion_payload = ['user_id', 'session_id', 'event_type', 'event_data', 'url', 'user_agent', 'ip_address']
        
        # Analytics processing
        analytics_record = ['event_id', 'user_id', 'session_id', 'event_type', 'event_data', 'timestamp']
        
        # Reporting
        summary_view = ['event_id', 'user_id', 'event_type', 'timestamp']
        
        # Data export
        csv_export = ['event_id', 'user_id', 'session_id', 'event_type', 'url', 'timestamp']
```

### Processing Pipeline

```python
# analytics/processor.py
from generated.pydantic.analytics_models import (
    UserEvent, UserEventIngestionPayload, UserEventAnalyticsRecord
)
import asyncio
from typing import List

class EventProcessor:
    """Process user events for analytics"""
    
    async def ingest_events(self, raw_events: List[dict]) -> List[UserEvent]:
        """Ingest and validate raw event data"""
        events = []
        
        for raw_event in raw_events:
            try:
                # Validate incoming data
                payload = UserEventIngestionPayload(**raw_event)
                
                # Create full event record
                event = UserEvent(
                    event_id=generate_event_id(),
                    **payload.dict()
                )
                
                events.append(event)
                
            except ValidationError as e:
                logger.error(f"Invalid event data: {e}")
                continue
        
        return events
    
    async def process_for_analytics(self, events: List[UserEvent]) -> List[UserEventAnalyticsRecord]:
        """Convert events to analytics format"""
        return [
            UserEventAnalyticsRecord(
                event_id=event.event_id,
                user_id=event.user_id,
                session_id=event.session_id,
                event_type=event.event_type,
                event_data=event.event_data,
                timestamp=event.timestamp
            )
            for event in events
        ]
```

## Microservice Architecture

Example of using Schema Gen across multiple microservices with shared schemas.

### Shared Schema Repository

```python
# shared-schemas/user_profile.py
from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime

@Schema
class UserProfile:
    """Shared user profile schema across services"""
    
    user_id: int = Field(
        primary_key=True,
        description="User identifier"
    )
    
    username: str = Field(
        unique=True,
        min_length=3,
        max_length=30
    )
    
    email: str = Field(
        format="email",
        unique=True
    )
    
    full_name: str = Field(
        max_length=100,
        description="User's display name"
    )
    
    avatar_url: Optional[str] = Field(
        default=None,
        format="uri",
        description="Profile picture URL"
    )
    
    is_verified: bool = Field(
        default=False,
        description="Email verification status"
    )
    
    created_at: datetime = Field(auto_now_add=True)
    updated_at: datetime = Field(auto_now=True)
    
    class Variants:
        # Service-specific views
        auth_service = ['user_id', 'username', 'email', 'is_verified']
        profile_service = ['user_id', 'username', 'email', 'full_name', 'avatar_url', 'updated_at']
        notification_service = ['user_id', 'username', 'email', 'full_name']
        
        # API contracts
        public_api = ['user_id', 'username', 'full_name', 'avatar_url']
        internal_api = ['user_id', 'username', 'email', 'full_name', 'avatar_url', 'is_verified']
        
        # Event payloads
        user_created_event = ['user_id', 'username', 'email', 'created_at']
        user_updated_event = ['user_id', 'username', 'email', 'full_name', 'avatar_url', 'updated_at']
```

### Service-Specific Usage

```python
# auth-service/handlers.py
from generated.pydantic.user_profile_models import (
    UserProfileAuthService, UserProfileUserCreatedEvent
)

async def create_user(user_data: dict) -> UserProfileAuthService:
    """Create user in auth service"""
    # Validate incoming data with service-specific view
    profile = UserProfileAuthService(**user_data)
    
    # Save to database
    await save_user_profile(profile)
    
    # Publish event with event-specific data
    event = UserProfileUserCreatedEvent(
        user_id=profile.user_id,
        username=profile.username,
        email=profile.email,
        created_at=datetime.now()
    )
    await publish_event("user.created", event)
    
    return profile
```

```python
# profile-service/handlers.py  
from generated.pydantic.user_profile_models import (
    UserProfileProfileService, UserProfilePublicApi
)

async def get_public_profile(user_id: int) -> UserProfilePublicApi:
    """Get public user profile"""
    # Get full profile from database
    full_profile = await get_user_profile(user_id)
    
    # Convert to public view
    return UserProfilePublicApi(
        user_id=full_profile.user_id,
        username=full_profile.username,
        full_name=full_profile.full_name,
        avatar_url=full_profile.avatar_url
    )
```

This demonstrates how Schema Gen enables:
- **Consistent data models** across services
- **Type-safe service communication** 
- **Clear API contracts** between teams
- **Automated validation** at service boundaries
- **Version control** of schema changes