from __future__ import annotations

import json
import random
from typing import Any

import numpy as np
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..ml.prefix_cf import FeatureSpace, PrefixCFModel
from ..ml.pbcf_nmf_mongo import PBCFEngineMongo
from ..models_mongo import Product


class RecommenderMongo:
    """MongoDB version of the recommender service."""

    def __init__(self):
        self.feature_space: FeatureSpace | None = None
        self.model: PrefixCFModel | None = None
        self.item_vectors: dict[str, np.ndarray] = {}
        self.pbcf = PBCFEngineMongo(k=6, iters=40)
        self._rating_count = 0

    async def refresh(self, db: AsyncIOMotorDatabase) -> None:
        """Refresh the feature space and models from the database."""
        products_cursor = db.products.find()
        products = [Product(**p) for p in await products_cursor.to_list(length=None)]

        self.feature_space = FeatureSpace.build(products)
        self.model = PrefixCFModel(self.feature_space)
        self.item_vectors = {str(p.id): self.feature_space.vectorize(p) for p in products}
        await self._refresh_pbcf(db)

    async def _refresh_pbcf(self, db: AsyncIOMotorDatabase) -> None:
        """Refresh PBCF if new ratings have been added."""
        count = await db.prefix_ratings.count_documents({})
        if count != self._rating_count:
            self._rating_count = count
            await self.pbcf.train(db)

    def load_state(self, session: dict[str, Any]) -> dict:
        """Load state from session document."""
        state = session.get("state", {})
        if not state:
            assert self.model is not None
            state = self.model.init_state()
        return state

    async def save_state(self, db: AsyncIOMotorDatabase, session_id: str, state: dict) -> None:
        """Save state to session document."""
        sid: str | ObjectId = session_id
        if ObjectId.is_valid(session_id):
            sid = ObjectId(session_id)
        await db.sessions.update_one(
            {"_id": sid},
            {"$set": {"state": state}}
        )

    async def update_with_selection(
        self,
        db: AsyncIOMotorDatabase,
        session_id: str,
        session: dict[str, Any],
        product: Product,
        is_exception: bool
    ) -> None:
        """Update model with user selection."""
        assert self.model is not None
        state = self.load_state(session)
        self.model.update_with_selection(state, product, is_exception)
        await self.save_state(db, session_id, state)

    async def update_with_prefix_rating(
        self,
        db: AsyncIOMotorDatabase,
        session_id: str,
        session: dict[str, Any],
        rating: int
    ) -> None:
        """Update model with prefix rating."""
        assert self.model is not None
        state = self.load_state(session)
        self.model.update_with_prefix_rating(state, rating)
        await self.save_state(db, session_id, state)

    async def recommend(
        self,
        db: AsyncIOMotorDatabase,
        session_id: str,
        session: dict[str, Any],
        limit: int = 2
    ) -> dict:
        """Generate recommendations for a session."""
        assert self.model is not None
        if not self.item_vectors:
            await self.refresh(db)
        await self._refresh_pbcf(db)

        state = self.load_state(session)

        # Session stores selection document IDs; resolve to selected product IDs.
        selection_ids = session.get("selections", [])
        selected_product_ids: set[str] = set()
        if selection_ids:
            selection_object_ids = [ObjectId(sid) for sid in selection_ids if ObjectId.is_valid(sid)]
            if selection_object_ids:
                selections = await db.selections.find(
                    {"_id": {"$in": selection_object_ids}},
                    {"product_id": 1},
                ).to_list(length=None)
                selected_product_ids = {str(row.get("product_id")) for row in selections if row.get("product_id")}

        # Get candidate products (not already selected)
        excluded_object_ids = [ObjectId(pid) for pid in selected_product_ids if ObjectId.is_valid(pid)]
        products_cursor = db.products.find({"_id": {"$nin": excluded_object_ids}})
        candidates = [Product(**p) for p in await products_cursor.to_list(length=None)]

        # Get predicted ratings from PBCF
        user_id = str(session["user_id"])
        predicted_ratings = await self.pbcf.predict_user_ratings(db, user_id)

        # Build current prefix
        current_prefix = "-".join(sorted(selected_product_ids)) if selected_product_ids else ""

        # Score candidates
        scored = []
        for product in candidates:
            vec = self.item_vectors.get(str(product.id))
            if vec is None:
                continue

            # Use PBCF prediction if available, otherwise fall back to content-based
            prefix_key = f"{current_prefix}-{product.id}" if current_prefix else str(product.id)
            if prefix_key in predicted_ratings:
                score = predicted_ratings[prefix_key]
            else:
                score = self.model.score_item(state, vec)

            scored.append((score, product, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        strong = scored[:limit]

        # Select wildcard from diverse pool
        wildcard = None
        if scored:
            diverse_pool = scored[-max(10, len(scored) // 8):]
            wildcard = random.choice(diverse_pool)[1]

        # Calculate metrics
        selected_vecs = [
            self.item_vectors[sid]
            for sid in selected_product_ids
            if sid in self.item_vectors
        ]
        coherence = self.model.coherence_score(selected_vecs)
        predicted_prefix = self.model.predict_prefix_rating(state)

        return {
            "strong": [p for _, p, _ in strong],
            "wildcard": wildcard,
            "coherence_score": coherence,
            "predicted_prefix_rating": predicted_prefix,
        }

    async def get_pbcf_stats(self, db: AsyncIOMotorDatabase) -> dict:
        """Get PBCF model statistics."""
        await self._refresh_pbcf(db)
        return self.pbcf.get_stats()


# Global recommender instance
recommender_mongo = RecommenderMongo()
