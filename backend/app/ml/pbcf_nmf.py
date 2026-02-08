from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
from sqlalchemy.orm import Session

from ..models import PrefixRating, Selection, Session as UserSession


@dataclass
class PBCFArtifacts:
    prefix_keys: list[str]
    user_ids: list[int]
    ratings: np.ndarray  # shape (n_prefix, n_users) with np.nan for missing
    mask: np.ndarray  # True where rating exists


class PBCFEngine:
    """
    Prefix-Based Collaborative Filtering using NMF with missing-value handling
    as described in Yu & Riedl (2014).
    """

    def __init__(self, k: int = 6, iters: int = 50, seed: int = 42):
        self.k = k
        self.iters = iters
        self.rng = np.random.default_rng(seed)
        self.artifacts: PBCFArtifacts | None = None
        self.W: np.ndarray | None = None
        self.H: np.ndarray | None = None

    def _prefix_key_for_rating(self, db: Session, rating: PrefixRating) -> str | None:
        selections = (
            db.query(Selection)
            .filter(Selection.session_id == rating.session_id)
            .filter(Selection.created_at <= rating.created_at)
            .order_by(Selection.created_at.asc())
            .all()
        )
        if not selections:
            return None
        return "-".join(str(sel.product_id) for sel in selections)

    def build_matrix(self, db: Session) -> PBCFArtifacts | None:
        ratings = db.query(PrefixRating).order_by(PrefixRating.created_at.asc()).all()
        if not ratings:
            return None

        prefix_keys: list[str] = []
        user_ids: list[int] = []
        key_index: dict[str, int] = {}
        user_index: dict[int, int] = {}

        # Collect latest rating per (prefix, user)
        latest: dict[tuple[str, int], tuple[datetime, int]] = {}

        for rating in ratings:
            session = db.query(UserSession).filter(UserSession.id == rating.session_id).first()
            if not session:
                continue
            key = self._prefix_key_for_rating(db, rating)
            if not key:
                continue
            user_id = session.user_id
            stamp = rating.created_at
            prev = latest.get((key, user_id))
            if prev is None or stamp > prev[0]:
                latest[(key, user_id)] = (stamp, rating.rating)

        for key, user_id in latest.keys():
            if key not in key_index:
                key_index[key] = len(prefix_keys)
                prefix_keys.append(key)
            if user_id not in user_index:
                user_index[user_id] = len(user_ids)
                user_ids.append(user_id)

        if not prefix_keys or not user_ids:
            return None

        R = np.full((len(prefix_keys), len(user_ids)), np.nan, dtype=np.float32)
        for (key, user_id), (_, rating_value) in latest.items():
            i = key_index[key]
            j = user_index[user_id]
            R[i, j] = float(rating_value)

        mask = ~np.isnan(R)
        return PBCFArtifacts(prefix_keys=prefix_keys, user_ids=user_ids, ratings=R, mask=mask)

    def train(self, db: Session) -> None:
        artifacts = self.build_matrix(db)
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

    def predict_user_ratings(self, db: Session, user_id: int) -> dict[str, float]:
        if self.artifacts is None or self.W is None:
            self.train(db)
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
