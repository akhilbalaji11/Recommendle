from __future__ import annotations

from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field
from bson import ObjectId


class ProductImageOut(BaseModel):
    url: str
    alt: Optional[str] = None
    position: Optional[int] = None


class ProductOut(BaseModel):
    id: str  # MongoDB ObjectId as string
    title: str
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    tags: list[str] = []
    options: dict[str, list[str]] = {}
    description: Optional[str] = None
    url: Optional[str] = None
    images: list[ProductImageOut] = []


class UserCreate(BaseModel):
    name: str


class UserOut(BaseModel):
    id: str  # MongoDB ObjectId as string
    name: str


class SessionCreate(BaseModel):
    user_id: str  # MongoDB ObjectId as string


class SessionOut(BaseModel):
    id: str  # MongoDB ObjectId as string
    user_id: str  # MongoDB ObjectId as string
    created_at: datetime


class SelectionCreate(BaseModel):
    product_id: str  # MongoDB ObjectId as string
    is_exception: bool = False


class PrefixRatingCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    tags: list[str] = []


class RecommendationOut(BaseModel):
    strong: list[ProductOut]
    wildcard: ProductOut | None = None
    coherence_score: float
    predicted_prefix_rating: float
