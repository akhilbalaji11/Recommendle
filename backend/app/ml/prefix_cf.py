from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable, Any

import numpy as np

# Try to import MongoDB models, fall back to SQLAlchemy for backward compatibility
try:
    from ..models_mongo import Product
except ImportError:
    from ..models import Product


@dataclass
class FeatureSpace:
    feature_index: dict[str, int]
    mean_price: float
    std_price: float

    @classmethod
    def build(cls, products: Iterable[Product]) -> "FeatureSpace":
        feature_index: dict[str, int] = {}
        prices = []

        def add_feature(name: str):
            if name not in feature_index:
                feature_index[name] = len(feature_index)

        for product in products:
            # Handle both dict-like and attribute access
            vendor = product.get("vendor") if isinstance(product, dict) else getattr(product, "vendor", None)
            product_type = product.get("product_type") if isinstance(product, dict) else getattr(product, "product_type", None)
            tags = product.get("tags", []) if isinstance(product, dict) else (product.tags() if callable(getattr(product, "tags", None)) else getattr(product, "tags", []))
            options = product.get("options", {}) if isinstance(product, dict) else (product.options() if callable(getattr(product, "options", None)) else getattr(product, "options", {}))
            price_min = product.get("price_min") if isinstance(product, dict) else getattr(product, "price_min", None)
            price_max = product.get("price_max") if isinstance(product, dict) else getattr(product, "price_max", None)

            if vendor:
                add_feature(f"vendor::{vendor.lower()}")
            if product_type:
                add_feature(f"type::{product_type.lower()}")
            for tag in tags:
                add_feature(f"tag::{tag.lower()}")
            for opt_name, opt_values in options.items():
                for value in opt_values:
                    add_feature(f"opt::{opt_name.lower()}::{value.lower()}")
            if price_min is not None:
                prices.append(price_min)
            if price_max is not None:
                prices.append(price_max)

        mean_price = float(np.mean(prices)) if prices else 0.0
        std_price = float(np.std(prices)) if prices else 1.0
        if std_price == 0:
            std_price = 1.0

        add_feature("price_min_z")
        add_feature("price_max_z")

        return cls(feature_index=feature_index, mean_price=mean_price, std_price=std_price)

    def vectorize(self, product: Any) -> np.ndarray:
        """Vectorize a product (works with both MongoDB and SQLAlchemy models)."""
        vec = np.zeros(len(self.feature_index), dtype=np.float32)

        def set_feature(name: str, value: float = 1.0):
            idx = self.feature_index.get(name)
            if idx is not None:
                vec[idx] = value

        # Handle both dict-like and attribute access
        vendor = product.get("vendor") if isinstance(product, dict) else getattr(product, "vendor", None)
        product_type = product.get("product_type") if isinstance(product, dict) else getattr(product, "product_type", None)
        tags = product.get("tags", []) if isinstance(product, dict) else (product.tags() if callable(getattr(product, "tags", None)) else getattr(product, "tags", []))
        options = product.get("options", {}) if isinstance(product, dict) else (product.options() if callable(getattr(product, "options", None)) else getattr(product, "options", {}))
        price_min = product.get("price_min") if isinstance(product, dict) else getattr(product, "price_min", None)
        price_max = product.get("price_max") if isinstance(product, dict) else getattr(product, "price_max", None)

        if vendor:
            set_feature(f"vendor::{vendor.lower()}")
        if product_type:
            set_feature(f"type::{product_type.lower()}")
        for tag in tags:
            set_feature(f"tag::{tag.lower()}")
        for opt_name, opt_values in options.items():
            for value in opt_values:
                set_feature(f"opt::{opt_name.lower()}::{value.lower()}")

        if price_min is not None:
            z = (price_min - self.mean_price) / self.std_price
            set_feature("price_min_z", float(z))
        if price_max is not None:
            z = (price_max - self.mean_price) / self.std_price
            set_feature("price_max_z", float(z))

        return vec


class PrefixCFModel:
    def __init__(self, feature_space: FeatureSpace):
        self.feature_space = feature_space

    def init_state(self) -> dict:
        return {
            "user_vec": [0.0] * len(self.feature_space.feature_index),
            "bias": 0.0,
            "count": 0,
            "exception_weight": 0.35,
            "decay": 0.85,
        }

    def update_with_selection(self, state: dict, product: Product, is_exception: bool) -> None:
        vec = self.feature_space.vectorize(product)
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        decay = float(state.get("decay", 0.85))
        weight = float(state.get("exception_weight", 0.35) if is_exception else 1.0)
        updated = decay * user_vec + weight * vec
        state["user_vec"] = updated.tolist()
        state["count"] = int(state.get("count", 0)) + 1

    def update_with_prefix_rating(self, state: dict, rating: int) -> None:
        predicted = self.predict_prefix_rating(state)
        error = float(rating) - predicted
        state["bias"] = float(state.get("bias", 0.0)) + 0.25 * error

    def predict_prefix_rating(self, state: dict) -> float:
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        bias = float(state.get("bias", 0.0))
        norm = float(np.linalg.norm(user_vec))
        base = 3.0 + 1.5 * math.tanh(norm / 3.0) + bias
        return float(min(5.0, max(1.0, base)))

    def score_item(self, state: dict, item_vec: np.ndarray) -> float:
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        bias = float(state.get("bias", 0.0))
        denom = (np.linalg.norm(user_vec) * np.linalg.norm(item_vec))
        similarity = 0.0
        if denom > 0:
            similarity = float(np.dot(user_vec, item_vec) / denom)
        score = 3.0 + 1.7 * similarity + bias
        return float(min(5.0, max(1.0, score)))

    def coherence_score(self, item_vecs: list[np.ndarray]) -> float:
        if len(item_vecs) < 2:
            return 0.0
        total = 0.0
        count = 0
        for i in range(len(item_vecs)):
            for j in range(i + 1, len(item_vecs)):
                denom = np.linalg.norm(item_vecs[i]) * np.linalg.norm(item_vecs[j])
                if denom == 0:
                    continue
                total += float(np.dot(item_vecs[i], item_vecs[j]) / denom)
                count += 1
        if count == 0:
            return 0.0
        return float((total / count + 1.0) / 2.0)  # scale to 0..1
