from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId


class PyObjectId(ObjectId):
    """Pydantic validator for MongoDB ObjectId."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.with_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    @classmethod
    def validate(cls, v, _info):
        if not isinstance(v, ObjectId):
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")
        return v


class MongoModel(BaseModel):
    """Base model for MongoDB documents."""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class ProductImage(MongoModel):
    url: str
    alt: Optional[str] = None
    position: int = 0


class Product(MongoModel):
    source_id: str = Field(..., index=True)
    title: str
    handle: str
    vendor: str
    product_type: str
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: str = "USD"
    tags: list[str] = Field(default_factory=list)
    options: dict[str, list[str]] = Field(default_factory=dict)
    description: Optional[str] = None
    url: Optional[str] = None
    images: list[ProductImage] = Field(default_factory=list)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )


class User(MongoModel):
    name: str
    sessions: list[PyObjectId] = Field(default_factory=list)


class Session(MongoModel):
    user_id: PyObjectId = Field(..., description="Reference to user")
    state: dict[str, Any] = Field(default_factory=dict, alias="state_json")
    selections: list[PyObjectId] = Field(default_factory=list)
    prefix_ratings: list[PyObjectId] = Field(default_factory=list)


class Selection(MongoModel):
    session_id: PyObjectId = Field(..., description="Reference to session")
    product_id: PyObjectId = Field(..., description="Reference to product")
    is_exception: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PrefixRating(MongoModel):
    session_id: PyObjectId = Field(..., description="Reference to session")
    rating: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Response models (DTOs)
class ProductOut(BaseModel):
    id: str
    source_id: str
    title: str
    handle: str
    vendor: str
    product_type: str
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: str
    tags: list[str]
    options: dict[str, list[str]]
    description: Optional[str] = None
    url: Optional[str] = None
    images: list[ProductImage]

    @classmethod
    def from_mongo(cls, product: Product) -> "ProductOut":
        return cls(
            id=str(product.id),
            source_id=product.source_id,
            title=product.title,
            handle=product.handle,
            vendor=product.vendor,
            product_type=product.product_type,
            price_min=product.price_min,
            price_max=product.price_max,
            currency=product.currency,
            tags=product.tags,
            options=product.options,
            description=product.description,
            url=product.url,
            images=product.images,
        )


class UserOut(BaseModel):
    id: str
    name: str
    created_at: datetime

    @classmethod
    def from_mongo(cls, user: User) -> "UserOut":
        return cls(id=str(user.id), name=user.name, created_at=user.created_at)


class SessionOut(BaseModel):
    id: str
    user_id: str
    created_at: datetime

    @classmethod
    def from_mongo(cls, session: Session) -> "SessionOut":
        return cls(
            id=str(session.id),
            user_id=str(session.user_id),
            created_at=session.created_at,
        )


class UserCreate(BaseModel):
    name: str


class SessionCreate(BaseModel):
    user_id: str


class SelectionCreate(BaseModel):
    product_id: str
    is_exception: bool = False


class PrefixRatingCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    strong: list[ProductOut]
    wildcard: Optional[ProductOut]
    coherence_score: float
    predicted_prefix_rating: float
