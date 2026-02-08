from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from bson import ObjectId

import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase


@dataclass
class PBCFArtifacts:
    prefix_keys: list[str]
    user_ids: list[str]  # MongoDB ObjectIds as strings
    ratings: np.ndarray  # shape (n_prefix, n_users) with np.nan for missing
    mask: np.ndarray  # True where rating exists


class PBCFEngineMongo:
    """
    Prefix-Based Collaborative Filtering using NMF with missing-value handling
    as described in Yu & Riedl (2014).

    MongoDB version of the PBCF engine.
    """

    def __init__(self, k: int = 6, iters: int = 50, seed: int = 42):
        self.k = k
        self.iters = iters
        self.rng = np.random.default_rng(seed)
        self.artifacts: PBCFArtifacts | None = None
        self.W: np.ndarray | None = None
        self.H: np.ndarray | None = None

    async def _prefix_key_for_rating(self, db: AsyncIOMotorDatabase, rating: dict[str, Any]) -> str | None:
        """Build prefix key from selections made before this rating."""
        session_id = rating["session_id"]
        rating_created_at = rating["created_at"]

        # Find all selections for this session that were created before this rating
        selections_cursor = db.selections.find({
            "session_id": session_id,
            "created_at": {"$lte": rating_created_at}
        }).sort("created_at", 1)

        selections = await selections_cursor.to_list(length=None)

        if not selections:
            return None

        return "-".join(str(sel["product_id"]) for sel in selections)

    async def build_matrix(self, db: AsyncIOMotorDatabase) -> PBCFArtifacts | None:
        """Build the prefix-rating matrix from MongoDB data."""
        # Get all prefix ratings ordered by creation time
        ratings_cursor = db.prefix_ratings.find().sort("created_at", 1)
        ratings = await ratings_cursor.to_list(length=None)

        if not ratings:
            return None

        prefix_keys: list[str] = []
        user_ids: list[str] = []
        key_index: dict[str, int] = {}
        user_index: dict[str, int] = {}

        # Collect latest rating per (prefix, user)
        latest: dict[tuple[str, str], tuple[datetime, int]] = {}

        for rating in ratings:
            session = await db.sessions.find_one({"_id": rating["session_id"]})
            if not session:
                continue

            key = await self._prefix_key_for_rating(db, rating)
            if not key:
                continue

            user_id = str(session["user_id"])
            stamp = rating["created_at"]

            prev = latest.get((key, user_id))
            if prev is None or stamp > prev[0]:
                latest[(key, user_id)] = (stamp, rating["rating"])

        # Build indices
        for key, user_id in latest.keys():
            if key not in key_index:
                key_index[key] = len(prefix_keys)
                prefix_keys.append(key)
            if user_id not in user_index:
                user_index[user_id] = len(user_ids)
                user_ids.append(user_id)

        if not prefix_keys or not user_ids:
            return None

        # Build rating matrix
        R = np.full((len(prefix_keys), len(user_ids)), np.nan, dtype=np.float32)
        for (key, user_id), (_, rating_value) in latest.items():
            i = key_index[key]
            j = user_index[user_id]
            R[i, j] = float(rating_value)

        mask = ~np.isnan(R)
        return PBCFArtifacts(prefix_keys=prefix_keys, user_ids=user_ids, ratings=R, mask=mask)

    async def train(self, db: AsyncIOMotorDatabase) -> None:
        """Train the NMF model on the prefix-rating matrix."""
        artifacts = await self.build_matrix(db)
        if artifacts is None:
            self.artifacts = None
            self.W = None
            self.H = None
            return

        R0 = artifacts.ratings
        mask = artifacts.mask
        n_prefix, n_users = R0.shape
        k = min(self.k, max(2, min(n_prefix, n_users)))

        W = self.rng.random((n_prefix, k), dtype=np.float32) + 0.1
        H = self.rng.random((k, n_users), dtype=np.float32) + 0.1
        eps = 1e-6

        for _ in range(self.iters):
            R = W @ H
            R[mask] = R0[mask]

            numerator_h = W.T @ R
            denominator_h = (W.T @ W @ H) + eps
            H *= numerator_h / denominator_h

            numerator_w = R @ H.T
            denominator_w = (W @ (H @ H.T)) + eps
            W *= numerator_w / denominator_w

        self.artifacts = artifacts
        self.W = W
        self.H = H

    async def predict_user_ratings(self, db: AsyncIOMotorDatabase, user_id: str) -> dict[str, float]:
        """Predict ratings for all prefixes for a given user."""
        if self.artifacts is None or self.W is None:
            await self.train(db)
        if self.artifacts is None or self.W is None:
            return {}

        artifacts = self.artifacts
        if user_id not in artifacts.user_ids:
            return {}

        user_idx = artifacts.user_ids.index(user_id)
        r0 = artifacts.ratings[:, user_idx].copy()
        mask = ~np.isnan(r0)

        k = self.W.shape[1]
        h = self.rng.random((k,), dtype=np.float32) + 0.1
        eps = 1e-6

        for _ in range(self.iters):
            r = self.W @ h
            r[mask] = r0[mask]
            numerator = self.W.T @ r
            denominator = (self.W.T @ self.W @ h) + eps
            h *= numerator / denominator

        r_pred = self.W @ h
        r_pred = np.clip(r_pred, 1.0, 5.0)
        return {key: float(r_pred[i]) for i, key in enumerate(artifacts.prefix_keys)}

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the trained model."""
        if self.artifacts is None or self.W is None:
            return {
                "trained": False,
                "prefix_count": 0,
                "user_count": 0,
                "ratings_count": 0,
                "missing_ratio": 1.0,
                "latent_dim": self.k,
            }

        ratings_count = int(self.artifacts.mask.sum())
        total = int(self.artifacts.ratings.size)
        missing_ratio = 1.0 - (ratings_count / total) if total else 1.0

        return {
            "trained": True,
            "prefix_count": len(self.artifacts.prefix_keys),
            "user_count": len(self.artifacts.user_ids),
            "ratings_count": ratings_count,
            "missing_ratio": round(missing_ratio, 3),
            "latent_dim": int(self.W.shape[1]),
        }
