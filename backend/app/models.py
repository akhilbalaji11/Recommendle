from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, unique=True, index=True)
    title = Column(String, index=True)
    handle = Column(String, index=True)
    vendor = Column(String, index=True)
    product_type = Column(String, index=True)
    price_min = Column(Float)
    price_max = Column(Float)
    currency = Column(String)
    tags_json = Column(Text)
    options_json = Column(Text)
    description = Column(Text)
    url = Column(String)

    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")

    def tags(self) -> list[str]:
        if not self.tags_json:
            return []
        return json.loads(self.tags_json)

    def options(self) -> dict[str, list[str]]:
        if not self.options_json:
            return {}
        return json.loads(self.options_json)


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    url = Column(String)
    alt = Column(String)
    position = Column(Integer)

    product = relationship("Product", back_populates="images")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    state_json = Column(Text)

    user = relationship("User", back_populates="sessions")
    selections = relationship("Selection", back_populates="session", cascade="all, delete-orphan")
    prefix_ratings = relationship("PrefixRating", back_populates="session", cascade="all, delete-orphan")


class Selection(Base):
    __tablename__ = "selections"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_exception = Column(Boolean, default=False)

    session = relationship("Session", back_populates="selections")


class PrefixRating(Base):
    __tablename__ = "prefix_ratings"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    rating = Column(Integer)
    tags_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="prefix_ratings")

    def tags(self) -> list[str]:
        if not self.tags_json:
            return []
        return json.loads(self.tags_json)
