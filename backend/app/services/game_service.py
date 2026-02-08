from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..ml.prefix_cf import PrefixCFModel
from ..services.recommender_mongo import recommender_mongo

# --------------- Feature-name humaniser ---------------

_REDUNDANT_TAGS = {
    "fountain pens", "fountain pen", "pens", "pen",
    "ink", "inks", "writing", "stationery",
    "hideoos", "bis-hidden", "products",
}


def humanize_feature(raw: str) -> str | None:
    """Convert an internal feature key to a human-readable label.

    Returns *None* for features that should be filtered out
    (e.g. overly-generic tags like 'fountain pens').
    """
    if raw.startswith("vendor::"):
        brand = raw.split("::", 1)[1].strip()
        return brand.title()
    if raw.startswith("type::"):
        t = raw.split("::", 1)[1].strip()
        if t.lower() in _REDUNDANT_TAGS:
            return None
        return t.title()
    if raw.startswith("tag::"):
        t = raw.split("::", 1)[1].strip()
        if t.lower() in _REDUNDANT_TAGS:
            return None
        return t.title()
    if raw.startswith("opt::"):
        parts = raw.split("::")
        if len(parts) == 3:
            opt_name = parts[1].strip().title()
            opt_val = parts[2].strip().title()
            return f"{opt_val} {opt_name}"
        return raw.replace("opt::", "").title()
    if raw == "price_min_z" or raw == "price_max_z":
        # Price labels are resolved upstream in the feature_weights loop
        return None
    return raw.title()


def humanize_feature_list(
    raw_list: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    """Return a de-duped, human-readable version of [(raw_name, weight)].

    Price entries arrive pre-labelled ("Lower/Higher Price Range") from the
    upstream feature_weights loop.  When both labels appear we keep only
    the stronger one (list is already sorted by descending abs-weight).
    """
    seen: set[str] = set()
    price_seen = False          # keep only the first (strongest) price tag
    result: list[tuple[str, float]] = []
    for raw, weight in raw_list:
        # Pre-labelled price entries pass through directly
        if raw in ("Lower Price Range", "Higher Price Range"):
            if price_seen:
                continue        # drop the weaker duplicate
            price_seen = True
            label = raw
        else:
            label = humanize_feature(raw)
        if label is None or label.lower() in seen:
            continue
        seen.add(label.lower())
        result.append((label, weight))
    return result


class GameService:
    """Sequential preference game service (50->10 onboarding, 5-round duel)."""

    def __init__(self):
        self.recommender = recommender_mongo
        self._indexes_ready = False

    async def _ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        if self._indexes_ready:
            return

        await db.games.create_index([("status", 1), ("created_at", -1)])
        await db.games.create_index([("player_name", 1), ("created_at", -1)])
        await db.game_rounds.create_index(
            [("game_id", 1), ("round_number", 1)],
            unique=True,
            name="game_id_round_number_unique_v2",
            partialFilterExpression={"game_id": {"$type": "objectId"}},
        )
        await db.game_rounds.create_index([("game_id", 1), ("created_at", -1)])
        self._indexes_ready = True

    async def _ensure_model(self, db: AsyncIOMotorDatabase) -> PrefixCFModel:
        if self.recommender.feature_space is None or self.recommender.model is None:
            await self.recommender.refresh(db)

        if self.recommender.feature_space is None or self.recommender.model is None:
            raise ValueError("Recommendation model is not initialized")

        return PrefixCFModel(self.recommender.feature_space)

    @staticmethod
    def _rng_for(game_id: str, round_number: int, salt: str) -> random.Random:
        seed_material = f"{game_id}:{round_number}:{salt}".encode("utf-8")
        seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16)
        return random.Random(seed)

    @staticmethod
    def _to_object_id(value: str, label: str) -> ObjectId:
        if not ObjectId.is_valid(value):
            raise ValueError(f"Invalid {label}")
        return ObjectId(value)

    @staticmethod
    def _product_card(product: dict[str, Any]) -> dict[str, Any]:
        image_url = None
        images = product.get("images") or []
        if images:
            image_url = images[0].get("url")

        return {
            "id": str(product["_id"]),
            "title": product.get("title"),
            "vendor": product.get("vendor"),
            "price_min": product.get("price_min"),
            "price_max": product.get("price_max"),
            "tags": product.get("tags", [])[:8],
            "image_url": image_url,
        }

    async def _get_game(self, db: AsyncIOMotorDatabase, game_id: str) -> dict[str, Any]:
        oid = self._to_object_id(game_id, "game ID")
        game = await db.games.find_one({"_id": oid})
        if game is None:
            raise ValueError("Game not found")
        return game

    async def _get_products_by_ids(
        self,
        db: AsyncIOMotorDatabase,
        ids: list[str],
        projection: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        object_ids = [ObjectId(pid) for pid in ids if ObjectId.is_valid(pid)]
        if not object_ids:
            return []
        cursor = db.products.find({"_id": {"$in": object_ids}}, projection)
        products = await cursor.to_list(length=len(object_ids))
        by_id = {str(p["_id"]): p for p in products}
        return [by_id[pid] for pid in ids if pid in by_id]

    async def _completed_pick_ids(self, db: AsyncIOMotorDatabase, game_id: str) -> list[str]:
        oid = self._to_object_id(game_id, "game ID")
        cursor = db.game_rounds.find(
            {"game_id": oid, "completed": True},
            {"human_pick_id": 1, "_id": 0},
        ).sort("round_number", 1)
        rounds = await cursor.to_list(length=None)
        return [row["human_pick_id"] for row in rounds if row.get("human_pick_id")]

    async def _current_selection_sequence(
        self,
        db: AsyncIOMotorDatabase,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        picked = await self._completed_pick_ids(db, str(game["_id"]))
        sequence = list(game.get("onboarding_selected_ids", [])) + picked
        if include_product_id:
            sequence.append(include_product_id)
        return sequence

    async def _metrics_for_state(
        self,
        db: AsyncIOMotorDatabase,
        model: PrefixCFModel,
        state: dict[str, Any],
        selected_ids: list[str],
    ) -> dict[str, float]:
        products = await self._get_products_by_ids(
            db,
            selected_ids,
            projection={
                "vendor": 1,
                "product_type": 1,
                "tags": 1,
                "options": 1,
                "price_min": 1,
                "price_max": 1,
            },
        )
        vectors = [self.recommender.feature_space.vectorize(p) for p in products]
        coherence_score = model.coherence_score(vectors)
        predicted_prefix_rating = model.predict_prefix_rating(state)
        return {
            "coherence_score": float(coherence_score),
            "predicted_prefix_rating": float(predicted_prefix_rating),
        }

    async def _all_products_for_scoring(self, db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
        cursor = db.products.find(
            {},
            {
                "title": 1,
                "vendor": 1,
                "price_min": 1,
                "price_max": 1,
                "tags": 1,
                "images": 1,
                "product_type": 1,
                "options": 1,
            },
        )
        return await cursor.to_list(length=None)

    def _diverse_onboarding_sample(self, all_products: list[dict[str, Any]], game_id: str) -> list[str]:
        if len(all_products) <= 50:
            return [str(p["_id"]) for p in all_products]

        rng = self._rng_for(game_id, 0, "onboarding")
        products = list(all_products)
        rng.shuffle(products)

        prices = sorted((p.get("price_min") or 0.0) for p in products)
        q1 = prices[len(prices) // 3]
        q2 = prices[(2 * len(prices)) // 3]

        low: list[dict[str, Any]] = []
        mid: list[dict[str, Any]] = []
        high: list[dict[str, Any]] = []
        for p in products:
            price = p.get("price_min") or 0.0
            if price <= q1:
                low.append(p)
            elif price <= q2:
                mid.append(p)
            else:
                high.append(p)

        def round_robin_pick(bucket: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
            by_vendor: dict[str, list[dict[str, Any]]] = {}
            for item in bucket:
                vendor = item.get("vendor") or "Unknown"
                by_vendor.setdefault(vendor, []).append(item)
            for vendor_items in by_vendor.values():
                rng.shuffle(vendor_items)
            vendor_keys = list(by_vendor.keys())
            rng.shuffle(vendor_keys)

            picks: list[dict[str, Any]] = []
            while len(picks) < target and vendor_keys:
                next_vendor_keys: list[str] = []
                for vendor in vendor_keys:
                    items = by_vendor[vendor]
                    if items:
                        picks.append(items.pop())
                        if len(picks) >= target:
                            break
                    if items:
                        next_vendor_keys.append(vendor)
                vendor_keys = next_vendor_keys
            return picks

        chosen = round_robin_pick(low, 17) + round_robin_pick(mid, 17) + round_robin_pick(high, 16)
        chosen_ids = {str(p["_id"]) for p in chosen}

        if len(chosen) < 50:
            remainder = [p for p in products if str(p["_id"]) not in chosen_ids]
            rng.shuffle(remainder)
            chosen.extend(remainder[: 50 - len(chosen)])

        chosen = chosen[:50]
        rng.shuffle(chosen)
        return [str(p["_id"]) for p in chosen]

    def _rank_candidates(
        self,
        model: PrefixCFModel,
        state: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> list[tuple[float, dict[str, Any]]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for product in products:
            vec = self.recommender.feature_space.vectorize(product)
            score = model.score_item(state, vec)
            scored.append((float(score), product))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)
        return scored

    def _build_round_candidates(
        self,
        game_id: str,
        round_number: int,
        scored: list[tuple[float, dict[str, Any]]],
    ) -> list[str]:
        rng = self._rng_for(game_id, round_number, "round_candidates")
        if len(scored) <= 10:
            ids = [str(p["_id"]) for _, p in scored]
            rng.shuffle(ids)
            return ids

        selected_ids: list[str] = []
        selected_set: set[str] = set()

        def add_from_pool(pool: list[tuple[float, dict[str, Any]]], target: int) -> None:
            pool_items = list(pool)
            rng.shuffle(pool_items)
            for _, product in pool_items:
                pid = str(product["_id"])
                if pid in selected_set:
                    continue
                selected_set.add(pid)
                selected_ids.append(pid)
                if len(selected_ids) >= target:
                    return

        likely = scored[:20]
        add_from_pool(likely, 6)

        near_boundary = scored[20:120] or scored[6:120]
        add_from_pool(near_boundary, 8)

        likely_vendors = {p.get("vendor") for _, p in scored[:10]}
        tail = scored[len(scored) // 2 :]
        diverse = [pair for pair in tail if pair[1].get("vendor") not in likely_vendors]
        if len(diverse) < 2:
            diverse = tail
        add_from_pool(diverse, 10)

        add_from_pool(scored, 10)

        selected_ids = selected_ids[:10]
        rng.shuffle(selected_ids)
        return selected_ids

    async def _persist_learning_selection(
        self,
        db: AsyncIOMotorDatabase,
        game: dict[str, Any],
        product_id: str,
        created_at: datetime | None = None,
    ) -> None:
        session_id = game.get("learning_session_id")
        if not session_id:
            return

        stamp = created_at or datetime.utcnow()
        selection_doc = {
            "session_id": session_id,
            "product_id": product_id,
            "is_exception": False,
            "created_at": stamp,
        }
        inserted = await db.selections.insert_one(selection_doc)
        await db.sessions.update_one(
            {"_id": ObjectId(session_id)},
            {"$push": {"selections": str(inserted.inserted_id)}},
        )

    async def create_game(
        self,
        db: AsyncIOMotorDatabase,
        player_name: str,
        total_rounds: int = 5,
    ) -> dict[str, Any]:
        await self._ensure_indexes(db)
        model = await self._ensure_model(db)

        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name is required")

        user_doc = {
            "name": f"{clean_name} (game)",
            "sessions": [],
            "created_at": datetime.utcnow(),
        }
        user_result = await db.users.insert_one(user_doc)
        user_id = str(user_result.inserted_id)

        session_doc = {
            "user_id": user_id,
            "state": model.init_state(),
            "selections": [],
            "prefix_ratings": [],
            "created_at": datetime.utcnow(),
        }
        session_result = await db.sessions.insert_one(session_doc)
        learning_session_id = str(session_result.inserted_id)

        await db.users.update_one(
            {"_id": user_result.inserted_id},
            {"$push": {"sessions": learning_session_id}},
        )

        now = datetime.utcnow()
        game_doc = {
            "player_name": clean_name,
            "status": "onboarding",
            "current_round": 0,
            "total_rounds": total_rounds,
            "human_score": 0,
            "ai_score": 0,
            "learning_user_id": user_id,
            "learning_session_id": learning_session_id,
            "model_state": model.init_state(),
            "onboarding_pool_ids": [],
            "onboarding_selected_ids": [],
            "onboarding_rating": None,
            "created_at": now,
            "updated_at": now,
        }

        result = await db.games.insert_one(game_doc)
        game = await db.games.find_one({"_id": result.inserted_id})
        assert game is not None

        return {
            "id": str(game["_id"]),
            "player_name": game["player_name"],
            "status": game["status"],
            "total_rounds": game["total_rounds"],
            "human_score": game["human_score"],
            "ai_score": game["ai_score"],
            "created_at": game["created_at"],
        }

    async def get_onboarding(self, db: AsyncIOMotorDatabase, game_id: str) -> dict[str, Any]:
        game = await self._get_game(db, game_id)
        if game.get("status") == "completed":
            raise ValueError("Game is already completed")

        pool_ids = game.get("onboarding_pool_ids") or []
        if not pool_ids:
            all_products = await self._all_products_for_scoring(db)
            pool_ids = self._diverse_onboarding_sample(all_products, game_id)
            await db.games.update_one(
                {"_id": game["_id"]},
                {"$set": {"onboarding_pool_ids": pool_ids, "updated_at": datetime.utcnow()}},
            )

        products = await self._get_products_by_ids(
            db,
            pool_ids,
            projection={
                "title": 1,
                "vendor": 1,
                "price_min": 1,
                "price_max": 1,
                "tags": 1,
                "images": 1,
            },
        )

        return {
            "game_id": game_id,
            "pool_size": len(products),
            "products": [self._product_card(p) for p in products],
        }

    async def submit_onboarding(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
        selected_product_ids: list[str],
        rating: int,
    ) -> dict[str, Any]:
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)

        if game.get("onboarding_selected_ids"):
            raise ValueError("Onboarding already submitted for this game")

        if len(selected_product_ids) != 10:
            raise ValueError("You must select exactly 10 products")
        if len(set(selected_product_ids)) != 10:
            raise ValueError("Duplicate products are not allowed")

        pool_ids = set(game.get("onboarding_pool_ids", []))
        if not pool_ids:
            raise ValueError("Onboarding pool is not initialized")
        if any(pid not in pool_ids for pid in selected_product_ids):
            raise ValueError("Selections must come from the onboarding pool")

        selected_products = await self._get_products_by_ids(
            db,
            selected_product_ids,
            projection={
                "title": 1,
                "vendor": 1,
                "price_min": 1,
                "price_max": 1,
                "tags": 1,
                "images": 1,
                "product_type": 1,
                "options": 1,
            },
        )
        if len(selected_products) != 10:
            raise ValueError("One or more selected products were not found")

        state = game.get("model_state") or model.init_state()
        for product in selected_products:
            model.update_with_selection(state, product, is_exception=False)
        model.update_with_prefix_rating(state, rating)

        metrics = await self._metrics_for_state(db, model, state, selected_product_ids)

        base_time = datetime.utcnow()
        for index, product_id in enumerate(selected_product_ids):
            stamp = base_time + timedelta(milliseconds=index)
            await self._persist_learning_selection(db, game, product_id, stamp)

        prefix_rating_doc = {
            "session_id": game["learning_session_id"],
            "rating": int(rating),
            "tags": [],
            "created_at": base_time + timedelta(milliseconds=1000),
        }
        rating_inserted = await db.prefix_ratings.insert_one(prefix_rating_doc)
        await db.sessions.update_one(
            {"_id": ObjectId(game["learning_session_id"])},
            {
                "$set": {"state": state},
                "$push": {"prefix_ratings": str(rating_inserted.inserted_id)},
            },
        )

        await db.games.update_one(
            {"_id": game["_id"]},
            {
                "$set": {
                    "status": "ready",
                    "model_state": state,
                    "onboarding_selected_ids": selected_product_ids,
                    "onboarding_rating": int(rating),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return {
            "accepted": True,
            "coherence_score": metrics["coherence_score"],
            "predicted_prefix_rating": metrics["predicted_prefix_rating"],
            "next_round": 1,
        }

    async def start_round(self, db: AsyncIOMotorDatabase, game_id: str) -> dict[str, Any]:
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)

        if len(game.get("onboarding_selected_ids", [])) != 10:
            raise ValueError("Onboarding is incomplete")
        if game["current_round"] >= game["total_rounds"]:
            raise ValueError("Game is complete")

        round_number = game["current_round"] + 1
        existing = await db.game_rounds.find_one(
            {"game_id": game["_id"], "round_number": round_number}
        )

        if existing and not existing.get("completed", False):
            products = await self._get_products_by_ids(
                db,
                existing.get("candidate_ids", []),
                projection={"title": 1, "vendor": 1, "price_min": 1, "price_max": 1, "tags": 1, "images": 1},
            )
            return {
                "round_number": round_number,
                "candidates": [self._product_card(p) for p in products],
                "pre_round_metrics": existing.get("pre_metrics", {"coherence_score": 0.0, "predicted_prefix_rating": 3.0}),
            }

        state = game.get("model_state") or model.init_state()
        selected_ids = await self._current_selection_sequence(db, game)
        used = set(selected_ids)

        all_products = await self._all_products_for_scoring(db)
        candidates_source = [p for p in all_products if str(p["_id"]) not in used]
        if len(candidates_source) < 10:
            raise ValueError("Not enough products left to generate a round")

        scored = self._rank_candidates(model, state, candidates_source)
        candidate_ids = self._build_round_candidates(game_id, round_number, scored)
        candidate_products = await self._get_products_by_ids(
            db,
            candidate_ids,
            projection={"title": 1, "vendor": 1, "price_min": 1, "price_max": 1, "tags": 1, "images": 1},
        )

        pre_metrics = await self._metrics_for_state(db, model, state, selected_ids)

        round_doc = {
            "game_id": game["_id"],
            "round_number": round_number,
            "candidate_ids": candidate_ids,
            "pre_metrics": pre_metrics,
            "completed": False,
            "created_at": datetime.utcnow(),
        }
        await db.game_rounds.update_one(
            {"game_id": game["_id"], "round_number": round_number},
            {"$setOnInsert": round_doc},
            upsert=True,
        )

        await db.games.update_one(
            {"_id": game["_id"]},
            {"$set": {"status": "playing", "updated_at": datetime.utcnow()}},
        )

        return {
            "round_number": round_number,
            "candidates": [self._product_card(p) for p in candidate_products],
            "pre_round_metrics": pre_metrics,
        }

    async def submit_pick(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
        round_number: int,
        product_id: str,
    ) -> dict[str, Any]:
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)

        if game["current_round"] >= game["total_rounds"]:
            raise ValueError("Game is already complete")
        if round_number != game["current_round"] + 1:
            raise ValueError("Invalid round number for current game state")
        if not ObjectId.is_valid(product_id):
            raise ValueError("Invalid product ID")

        round_doc = await db.game_rounds.find_one(
            {"game_id": game["_id"], "round_number": round_number}
        )
        if round_doc is None:
            raise ValueError("Round has not been started")
        if round_doc.get("completed", False):
            raise ValueError("Round has already been completed")

        candidate_ids = round_doc.get("candidate_ids", [])
        if product_id not in candidate_ids:
            raise ValueError("Selected product is not in this round's candidate set")

        candidate_products = await self._get_products_by_ids(
            db,
            candidate_ids,
            projection={
                "title": 1,
                "vendor": 1,
                "price_min": 1,
                "price_max": 1,
                "tags": 1,
                "images": 1,
                "product_type": 1,
                "options": 1,
            },
        )
        by_id = {str(p["_id"]): p for p in candidate_products}
        if product_id not in by_id:
            raise ValueError("Selected product does not exist")

        state = game.get("model_state") or model.init_state()
        scored = []
        for item in candidate_products:
            score = model.score_item(state, self.recommender.feature_space.vectorize(item))
            scored.append((float(score), item))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)

        ai_score, ai_pick_product = scored[0]
        ai_pick_id = str(ai_pick_product["_id"])
        ai_top3_ids = [str(p["_id"]) for _, p in scored[:3]]
        ai_correct = product_id in ai_top3_ids
        ai_exact = ai_pick_id == product_id
        human_points = 0 if ai_correct else 10
        ai_points = 10 if ai_correct else 0
        ai_rank_of_pick = next(
            (i + 1 for i, (_, p) in enumerate(scored) if str(p["_id"]) == product_id),
            len(scored),
        )

        human_pick_product = by_id[product_id]
        model.update_with_selection(state, human_pick_product, is_exception=False)

        await self._persist_learning_selection(db, game, product_id)
        await db.sessions.update_one(
            {"_id": ObjectId(game["learning_session_id"])},
            {"$set": {"state": state}},
        )

        selected_ids = await self._current_selection_sequence(db, game, include_product_id=product_id)
        post_metrics = await self._metrics_for_state(db, model, state, selected_ids)

        top_candidates = []
        for score, product in scored[:5]:
            card = self._product_card(product)
            card["score"] = float(score)
            top_candidates.append(card)

        # Build feature-level explanation
        human_vec = self.recommender.feature_space.vectorize(human_pick_product)
        ai_vec = self.recommender.feature_space.vectorize(ai_pick_product)
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)

        # Identify what features the user profile has learned to prefer
        inv_index = {v: k for k, v in self.recommender.feature_space.feature_index.items()}
        feature_weights = []
        for idx in range(len(user_vec)):
            w = float(user_vec[idx])
            if abs(w) > 0.05:
                fname = inv_index.get(idx, f"feature_{idx}")
                # Price z-scores: a negative weight means user prefers
                # cheaper pens; positive means pricier. Both are "likes".
                if fname in ("price_min_z", "price_max_z"):
                    price_label = "Lower Price Range" if w < 0 else "Higher Price Range"
                    feature_weights.append((price_label, abs(w)))
                else:
                    feature_weights.append((fname, w))
        feature_weights.sort(key=lambda x: abs(x[1]), reverse=True)
        top_positive = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w > 0][:8])
        top_negative = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w < 0][:5])

        # Human pick features
        human_features = [inv_index.get(i, f"f{i}") for i in range(len(human_vec)) if human_vec[i] > 0]
        ai_features = [inv_index.get(i, f"f{i}") for i in range(len(ai_vec)) if ai_vec[i] > 0]
        shared_raw = list(set(human_features) & set(ai_features))
        shared_features = [h for h in (humanize_feature(f) for f in shared_raw) if h is not None]

        # ── Hidden preference detection ──────────────────────────
        all_selected_ids = await self._current_selection_sequence(
            db, game, include_product_id=product_id
        )
        all_selected_products = await self._get_products_by_ids(
            db,
            all_selected_ids,
            projection={
                "vendor": 1, "product_type": 1, "tags": 1,
                "options": 1, "price_min": 1, "price_max": 1,
            },
        )
        hidden_raw = model.detect_hidden_preferences(state, all_selected_products)
        hidden_prefs = humanize_feature_list(
            [(h["feature"], round(h["latency"], 3)) for h in hidden_raw]
        )
        # Generate human-readable hints
        hidden_hints: list[str] = []
        for h in hidden_raw[:2]:
            label = humanize_feature(h["feature"])
            if label:
                hidden_hints.append(
                    f"The AI notices a hidden pattern: your picks tend to share \"{label}\" "
                    f"even though you may not have targeted it."
                )

        if ai_correct:
            if ai_exact:
                reason = f"The AI predicted your exact pick! It ranked this product #1 out of {len(candidate_products)} candidates based on your preference profile."
            else:
                match_rank = ai_top3_ids.index(product_id) + 1
                reason = f"Your pick was the AI's #{match_rank} prediction. The AI successfully identified your choice within its top 3 candidates."
        else:
            reason = f"Your pick ranked #{ai_rank_of_pick} in the AI's predictions. The model's top pick was '{ai_pick_product.get('title', 'Unknown')}', which scored {ai_score:.2f} based on feature similarity to your profile."

        await db.game_rounds.update_one(
            {"_id": round_doc["_id"]},
            {
                "$set": {
                    "human_pick_id": product_id,
                    "ai_pick_id": ai_pick_id,
                    "ai_confidence": float(ai_score),
                    "ai_top_k": [
                        {"product_id": str(product["_id"]), "score": float(score)}
                        for score, product in scored[:5]
                    ],
                    "ai_top3_ids": ai_top3_ids,
                    "ai_rank_of_pick": ai_rank_of_pick,
                    "ai_correct": ai_correct,
                    "human_points": human_points,
                    "ai_points": ai_points,
                    "post_metrics": post_metrics,
                    "completed": True,
                    "completed_at": datetime.utcnow(),
                }
            },
        )

        new_current_round = game["current_round"] + 1
        new_human_total = game["human_score"] + human_points
        new_ai_total = game["ai_score"] + ai_points
        game_complete = new_current_round >= game["total_rounds"]

        await db.games.update_one(
            {"_id": game["_id"]},
            {
                "$set": {
                    "current_round": new_current_round,
                    "human_score": new_human_total,
                    "ai_score": new_ai_total,
                    "status": "completed" if game_complete else "playing",
                    "model_state": state,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        return {
            "round_number": round_number,
            "human_pick": self._product_card(human_pick_product),
            "ai_pick": {
                **self._product_card(ai_pick_product),
                "score": float(ai_score),
            },
            "ai_correct": ai_correct,
            "ai_exact": ai_exact,
            "ai_rank_of_pick": ai_rank_of_pick,
            "ai_top3_ids": ai_top3_ids,
            "human_points": human_points,
            "ai_points": ai_points,
            "total_human_score": new_human_total,
            "total_ai_score": new_ai_total,
            "ai_explanation": {
                "reason": reason,
                "top_candidates": top_candidates,
                "learned_preferences": top_positive,
                "learned_dislikes": top_negative,
                "shared_features": shared_features[:6],
                "hidden_preferences": hidden_prefs,
                "hidden_preference_hints": hidden_hints,
            },
            "post_round_metrics": post_metrics,
            "game_complete": game_complete,
        }

    async def get_game_summary(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
    ) -> dict[str, Any]:
        """Return post-game insights: round-by-round stats, learned profile, top-5 recs."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)

        if game.get("status") != "completed":
            raise ValueError("Game is not yet completed")

        # Load all rounds
        cursor = db.game_rounds.find(
            {"game_id": game["_id"], "completed": True}
        ).sort("round_number", 1)
        rounds = await cursor.to_list(length=None)

        # Round-by-round data for charts
        round_stats = []
        cumulative_ai = 0
        cumulative_human = 0
        for rnd in rounds:
            ai_correct = rnd.get("ai_correct", False)
            cumulative_ai += rnd.get("ai_points", 0)
            cumulative_human += rnd.get("human_points", 0)
            post = rnd.get("post_metrics", {})
            round_stats.append({
                "round_number": rnd["round_number"],
                "ai_correct": ai_correct,
                "ai_rank_of_pick": rnd.get("ai_rank_of_pick", None),
                "ai_confidence": rnd.get("ai_confidence", 0),
                "coherence": post.get("coherence_score", 0),
                "predicted_rating": post.get("predicted_prefix_rating", 3.0),
                "cumulative_ai": cumulative_ai,
                "cumulative_human": cumulative_human,
            })

        # Model's learned preferences from the final state
        state = game.get("model_state") or model.init_state()
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        inv_index = {v: k for k, v in self.recommender.feature_space.feature_index.items()}

        feature_weights = []
        for idx in range(len(user_vec)):
            w = float(user_vec[idx])
            if abs(w) > 0.05:
                fname = inv_index.get(idx, f"feature_{idx}")
                if fname in ("price_min_z", "price_max_z"):
                    price_label = "Lower Price Range" if w < 0 else "Higher Price Range"
                    feature_weights.append((price_label, abs(w)))
                else:
                    feature_weights.append((fname, w))
        feature_weights.sort(key=lambda x: abs(x[1]), reverse=True)

        learned_likes = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w > 0][:10])
        learned_dislikes = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w < 0][:5])

        # Top-5 recommended products from the full catalog
        all_products = await self._all_products_for_scoring(db)
        scored = self._rank_candidates(model, state, all_products)
        top5_recs = []
        for score, product in scored[:5]:
            card = self._product_card(product)
            card["score"] = float(score)
            top5_recs.append(card)
        top5_ids = {r["id"] for r in top5_recs}

        # ── Hidden preference discovery (final) ─────────────────
        all_selected_ids = await self._current_selection_sequence(db, game)
        all_selected_products = await self._get_products_by_ids(
            db,
            all_selected_ids,
            projection={
                "vendor": 1, "product_type": 1, "tags": 1,
                "options": 1, "price_min": 1, "price_max": 1,
            },
        )
        hidden_raw = model.detect_hidden_preferences(state, all_selected_products)
        hidden_prefs = humanize_feature_list(
            [(h["feature"], round(h["latency"], 3)) for h in hidden_raw]
        )

        # Remove hidden prefs that already appear in learned_likes
        learned_names = {name.lower() for name, _ in learned_likes}
        hidden_prefs = [
            (n, w) for n, w in hidden_prefs
            if n.lower() not in learned_names
        ]

        # Hidden gem products — pens the user didn't see but match latent tastes
        # Exclude any products already in the top-5 recommendations
        hidden_gem_results = model.get_hidden_gem_products(
            state, all_selected_products, all_products, top_n=10
        )
        hidden_gems_cards = []
        for gem_score, gem_product, matched_features in hidden_gem_results:
            pid = str(gem_product["_id"])
            if pid in top5_ids:
                continue
            card = self._product_card(gem_product)
            card["score"] = round(float(gem_score), 3)
            hidden_gems_cards.append(card)
            if len(hidden_gems_cards) >= 5:
                break

        # Build narrative explanation
        hidden_gems_explanation = ""
        if hidden_prefs:
            feature_names = [name for name, _ in hidden_prefs[:3]]
            if len(feature_names) == 1:
                hidden_gems_explanation = (
                    f"Although you may not have noticed, your choices reveal a hidden "
                    f"affinity for \"{feature_names[0]}\". The pens below match this "
                    f"latent pattern the AI discovered in your selections."
                )
            else:
                joined = ", ".join(f'\"{n}\"' for n in feature_names[:-1])
                joined += f' and \"{feature_names[-1]}\"'
                hidden_gems_explanation = (
                    f"Your choices reveal hidden patterns the AI detected: {joined}. "
                    f"These features appeared across your selections even though you "
                    f"likely weren't targeting them. The pens below match these "
                    f"latent preferences."
                )

        # Accuracy summary
        total = len(rounds)
        correct = sum(1 for r in rounds if r.get("ai_correct"))
        exact = sum(1 for r in rounds if r.get("ai_pick_id") == r.get("human_pick_id"))

        return {
            "game_id": str(game["_id"]),
            "player_name": game["player_name"],
            "total_rounds": total,
            "human_score": game["human_score"],
            "ai_score": game["ai_score"],
            "accuracy": {
                "top3_correct": correct,
                "exact_correct": exact,
                "top3_rate": correct / total if total else 0,
                "exact_rate": exact / total if total else 0,
            },
            "round_stats": round_stats,
            "learned_preferences": learned_likes,
            "learned_dislikes": learned_dislikes,
            "top5_recommendations": top5_recs,
            "hidden_preferences": hidden_prefs,
            "hidden_gems_products": hidden_gems_cards,
            "hidden_gems_explanation": hidden_gems_explanation,
        }

    async def get_game_status(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
    ) -> dict[str, Any]:
        game = await self._get_game(db, game_id)

        active_round = await db.game_rounds.find_one(
            {"game_id": game["_id"], "completed": False},
            {"round_number": 1},
            sort=[("round_number", 1)],
        )

        return {
            "id": str(game["_id"]),
            "player_name": game["player_name"],
            "status": game["status"],
            "current_round": int(game.get("current_round", 0)),
            "total_rounds": int(game.get("total_rounds", 10)),
            "human_score": int(game.get("human_score", 0)),
            "ai_score": int(game.get("ai_score", 0)),
            "onboarding_complete": len(game.get("onboarding_selected_ids", [])) == 10,
            "onboarding_selected_count": len(game.get("onboarding_selected_ids", [])),
            "round_in_progress": active_round.get("round_number") if active_round else None,
        }

    async def get_leaderboard(self, db: AsyncIOMotorDatabase, limit: int = 10) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"status": "completed"}},
            {"$addFields": {"score_difference": {"$subtract": ["$human_score", "$ai_score"]}}},
            {"$sort": {"score_difference": -1, "human_score": -1, "created_at": 1}},
            {"$limit": int(limit)},
        ]
        games = await db.games.aggregate(pipeline).to_list(length=limit)

        return [
            {
                "rank": index + 1,
                "player_name": game["player_name"],
                "human_score": int(game["human_score"]),
                "ai_score": int(game["ai_score"]),
                "score_difference": int(game["human_score"] - game["ai_score"]),
                "rounds_completed": int(game.get("current_round", 0)),
                "created_at": game["created_at"],
            }
            for index, game in enumerate(games)
        ]

    async def get_player_history(
        self,
        db: AsyncIOMotorDatabase,
        player_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return completed games for a given player, most recent first."""
        cursor = db.games.find(
            {"player_name": player_name, "status": "completed"},
        ).sort("created_at", -1).limit(limit)
        games = await cursor.to_list(length=limit)

        results: list[dict[str, Any]] = []
        for game in games:
            game_id = str(game["_id"])
            total = int(game.get("current_round", 0))
            h = int(game.get("human_score", 0))
            a = int(game.get("ai_score", 0))

            # Count AI correct rounds
            ai_correct = await db.game_rounds.count_documents(
                {"game_id": game["_id"], "completed": True, "ai_correct": True}
            )

            results.append({
                "game_id": game_id,
                "player_name": player_name,
                "human_score": h,
                "ai_score": a,
                "score_difference": h - a,
                "rounds_played": total,
                "ai_accuracy": ai_correct / total if total else 0,
                "created_at": game["created_at"],
            })

        return results


game_service = GameService()
