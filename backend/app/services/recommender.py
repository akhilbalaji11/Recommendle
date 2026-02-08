from __future__ import annotations

import json
import random
from typing import Iterable

import numpy as np

from sqlalchemy.orm import Session

from ..ml.prefix_cf import FeatureSpace, PrefixCFModel
from ..ml.pbcf_nmf import PBCFEngine
from ..models import Product, Session as UserSession, Selection, PrefixRating


class Recommender:
    def __init__(self):
        self.feature_space: FeatureSpace | None = None
        self.model: PrefixCFModel | None = None
        self.item_vectors: dict[int, np.ndarray] = {}
        self.pbcf = PBCFEngine(k=6, iters=40)
        self._rating_count = 0

    def refresh(self, db: Session) -> None:
        products = db.query(Product).all()
        self.feature_space = FeatureSpace.build(products)
        self.model = PrefixCFModel(self.feature_space)
        self.item_vectors = {product.id: self.feature_space.vectorize(product) for product in products}
        self._refresh_pbcf(db)

    def _refresh_pbcf(self, db: Session) -> None:
        count = db.query(PrefixRating).count()
        if count != self._rating_count:
            self._rating_count = count
            self.pbcf.train(db)

    def load_state(self, session: UserSession) -> dict:
        if session.state_json:
            return json.loads(session.state_json)
        assert self.model is not None
        return self.model.init_state()

    def save_state(self, session: UserSession, state: dict) -> None:
        session.state_json = json.dumps(state)

    def update_with_selection(self, session: UserSession, product: Product, is_exception: bool) -> None:
        assert self.model is not None
        state = self.load_state(session)
        self.model.update_with_selection(state, product, is_exception)
        self.save_state(session, state)

    def update_with_prefix_rating(self, session: UserSession, rating: int) -> None:
        assert self.model is not None
        state = self.load_state(session)
        self.model.update_with_prefix_rating(state, rating)
        self.save_state(session, state)

    def recommend(self, db: Session, session: UserSession, limit: int = 2) -> dict:
        assert self.model is not None
        if not self.item_vectors:
            self.refresh(db)
        self._refresh_pbcf(db)

        state = self.load_state(session)
        selected_ids = {s.product_id for s in session.selections}
        candidates = [p for p in db.query(Product).all() if p.id not in selected_ids]

        predicted_ratings = self.pbcf.predict_user_ratings(db, session.user_id)
        current_prefix = "-".join(str(s.product_id) for s in session.selections)

        scored = []
        for product in candidates:
            vec = self.item_vectors.get(product.id)
            if vec is None:
                continue
            # Prefix-based CF score when available; otherwise fallback to content-based score.
            prefix_key = f"{current_prefix}-{product.id}" if current_prefix else str(product.id)
            if prefix_key in predicted_ratings:
                score = predicted_ratings[prefix_key]
            else:
                score = self.model.score_item(state, vec)
            scored.append((score, product, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        strong = scored[:limit]

        wildcard = None
        if scored:
            diverse_pool = scored[-max(10, len(scored) // 8):]
            wildcard = random.choice(diverse_pool)[1]

        selected_vecs = [self.item_vectors[s.product_id] for s in session.selections if s.product_id in self.item_vectors]
        coherence = self.model.coherence_score(selected_vecs)
        predicted_prefix = self.model.predict_prefix_rating(state)

        return {
            "strong": [p for _, p, _ in strong],
            "wildcard": wildcard,
            "coherence_score": coherence,
            "predicted_prefix_rating": predicted_prefix,
        }

    def pbcf_stats(self, db: Session) -> dict:
        self._refresh_pbcf(db)
        artifacts = self.pbcf.artifacts
        if artifacts is None or self.pbcf.W is None:
            return {
                "trained": False,
                "prefix_count": 0,
                "user_count": 0,
                "ratings_count": 0,
                "missing_ratio": 1.0,
                "latent_dim": self.pbcf.k,
            }
        ratings_count = int(artifacts.mask.sum())
        total = int(artifacts.ratings.size)
        missing_ratio = 1.0 - (ratings_count / total) if total else 1.0
        return {
            "trained": True,
            "prefix_count": len(artifacts.prefix_keys),
            "user_count": len(artifacts.user_ids),
            "ratings_count": ratings_count,
            "missing_ratio": round(missing_ratio, 3),
            "latent_dim": int(self.pbcf.W.shape[1]),
        }


recommender = Recommender()
