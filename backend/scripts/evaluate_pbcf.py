from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.ml.prefix_cf import FeatureSpace


DATA_DIR = ROOT_DIR / "data"
PRODUCTS_JSON = DATA_DIR / "products.json"
REPORTS_DIR = ROOT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ProductLite:
    id: int
    title: str
    vendor: str | None
    product_type: str | None
    price_min: float | None
    price_max: float | None
    tags_json: list[str]
    options_json: dict[str, list[str]]

    def tags(self) -> list[str]:
        return self.tags_json or []

    def options(self) -> dict[str, list[str]]:
        return self.options_json or {}


def load_products() -> list[ProductLite]:
    raw = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    products: list[ProductLite] = []
    for item in raw:
        products.append(
            ProductLite(
                id=int(item.get("source_id")),
                title=item.get("title"),
                vendor=item.get("vendor"),
                product_type=item.get("product_type"),
                price_min=item.get("price_min"),
                price_max=item.get("price_max"),
                tags_json=item.get("tags", []),
                options_json=item.get("options", {}),
            )
        )
    return products


def build_prefix_matrix(prefix_ratings: list[tuple[str, int, float]]):
    prefix_keys: list[str] = []
    user_ids: list[int] = []
    key_index: dict[str, int] = {}
    user_index: dict[int, int] = {}

    for key, user_id, _ in prefix_ratings:
        if key not in key_index:
            key_index[key] = len(prefix_keys)
            prefix_keys.append(key)
        if user_id not in user_index:
            user_index[user_id] = len(user_ids)
            user_ids.append(user_id)

    R = np.full((len(prefix_keys), len(user_ids)), np.nan, dtype=np.float32)
    for key, user_id, rating in prefix_ratings:
        i = key_index[key]
        j = user_index[user_id]
        R[i, j] = float(rating)

    return prefix_keys, user_ids, R


def nmf_train(R0: np.ndarray, mask: np.ndarray, k: int = 6, iters: int = 60, seed: int = 42):
    rng = np.random.default_rng(seed)
    n_prefix, n_users = R0.shape
    k = min(k, max(2, min(n_prefix, n_users)))
    W = rng.random((n_prefix, k), dtype=np.float32) + 0.1
    H = rng.random((k, n_users), dtype=np.float32) + 0.1
    eps = 1e-6

    for _ in range(iters):
        R = W @ H
        R[mask] = R0[mask]
        numerator_h = W.T @ R
        denominator_h = (W.T @ W @ H) + eps
        H *= numerator_h / denominator_h
        numerator_w = R @ H.T
        denominator_w = (W @ (H @ H.T)) + eps
        W *= numerator_w / denominator_w

    return W, H


def nmf_predict_user(W: np.ndarray, r0: np.ndarray, iters: int = 60, seed: int = 42):
    rng = np.random.default_rng(seed)
    k = W.shape[1]
    h = rng.random((k,), dtype=np.float32) + 0.1
    mask = ~np.isnan(r0)
    eps = 1e-6

    for _ in range(iters):
        r = W @ h
        r[mask] = r0[mask]
        numerator = W.T @ r
        denominator = (W.T @ W @ h) + eps
        h *= numerator / denominator

    return W @ h


def simulate_sessions(products: list[ProductLite], feature_space: FeatureSpace, num_users: int, length: int, seed: int):
    rng = np.random.default_rng(seed)
    vectors = {p.id: feature_space.vectorize(p) for p in products}
    prefix_ratings: list[tuple[str, int, float]] = []
    user_choices: dict[int, list[int]] = {}

    for uid in range(num_users):
        pref = rng.normal(0, 1, size=len(feature_space.feature_index)).astype(np.float32)
        chosen: list[int] = []
        remaining = products.copy()
        random.shuffle(remaining)

        for _ in range(length):
            scored = []
            for p in remaining:
                vec = vectors[p.id]
                score = float(np.dot(pref, vec)) + rng.normal(0, 0.05)
                scored.append((score, p))
            scored.sort(key=lambda x: x[0], reverse=True)
            pick = scored[0][1]
            chosen.append(pick.id)
            remaining = [p for p in remaining if p.id != pick.id]

            util = [float(np.dot(pref, vectors[pid])) for pid in chosen]
            mean_util = float(np.mean(util))
            rating = 3.0 + 1.5 * math.tanh(mean_util / 3.0)
            rating = min(5.0, max(1.0, rating))
            prefix_key = "-".join(str(pid) for pid in chosen)
            prefix_ratings.append((prefix_key, uid, rating))

        user_choices[uid] = chosen

    return prefix_ratings, user_choices


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def run_trial(products, feature_space, num_users, session_length, seed):
    prefix_ratings, user_choices = simulate_sessions(products, feature_space, num_users, session_length, seed)
    prefix_keys, user_ids, R = build_prefix_matrix(prefix_ratings)
    mask = ~np.isnan(R)

    rng = np.random.default_rng(seed + 3)
    observed = np.argwhere(mask)
    rng.shuffle(observed)
    split = int(len(observed) * 0.8)
    train_idx = observed[:split]
    test_idx = observed[split:]

    train_mask = np.zeros_like(mask)
    train_mask[tuple(train_idx.T)] = True

    R_train = R.copy()
    R_train[~train_mask] = np.nan

    W, H = nmf_train(R_train, train_mask, k=6, iters=80, seed=seed + 5)
    R_pred = W @ H

    y_true = np.array([R[i, j] for i, j in test_idx], dtype=np.float32)
    y_pred = np.array([R_pred[i, j] for i, j in test_idx], dtype=np.float32)
    base_rmse = rmse(y_true, y_pred)

    # Learning curve (single user)
    user_example = 0
    user_col = user_ids.index(user_example)
    r_full = R[:, user_col]
    user_prefixes = [i for i in range(len(prefix_keys)) if not np.isnan(r_full[i])]

    rmse_curve: dict[int, float] = {}
    for k in range(1, min(len(user_prefixes), session_length) + 1):
        r0 = np.full_like(r_full, np.nan)
        known = user_prefixes[:k]
        r0[known] = r_full[known]
        r_pred = nmf_predict_user(W, r0, iters=60, seed=seed + 11)
        unknown = user_prefixes[k:]
        if not unknown:
            continue
        rmse_k = rmse(r_full[unknown], r_pred[unknown])
        rmse_curve[k] = rmse_k

    hit_curve: dict[int, float] = {}
    for k in range(1, session_length):
        hits = 0
        total = 0
        for uid in range(num_users):
            col = user_ids.index(uid)
            r_full_u = R[:, col]
            r0 = np.full_like(r_full_u, np.nan)
            prefix_indices = [i for i in range(len(prefix_keys)) if not np.isnan(r_full_u[i])]
            if len(prefix_indices) <= k:
                continue
            known = prefix_indices[:k]
            r0[known] = r_full_u[known]
            r_pred = nmf_predict_user(W, r0, iters=40, seed=seed + 17)

            current_prefix = "-".join(str(pid) for pid in user_choices[uid][:k])
            candidates = []
            for p in products:
                if p.id in user_choices[uid][:k]:
                    continue
                prefix_key = f"{current_prefix}-{p.id}" if current_prefix else str(p.id)
                if prefix_key in prefix_keys:
                    idx = prefix_keys.index(prefix_key)
                    candidates.append((r_pred[idx], p.id))
            if not candidates:
                continue
            candidates.sort(key=lambda x: x[0], reverse=True)
            predicted_next = candidates[0][1]
            true_next = user_choices[uid][k]
            hits += 1 if predicted_next == true_next else 0
            total += 1
        if total:
            hit_curve[k] = hits / total

    return base_rmse, rmse_curve, hit_curve


def aggregate_curves(curves: list[dict[int, float]]):
    all_keys = sorted({k for curve in curves for k in curve.keys()})
    avg = {}
    for k in all_keys:
        vals = [curve[k] for curve in curves if k in curve]
        if vals:
            avg[k] = float(np.mean(vals))
    return avg


def plot_curve(curve: dict[int, float], title: str, ylabel: str, path: Path):
    xs = list(curve.keys())
    ys = list(curve.values())
    plt.figure(figsize=(6, 4))
    plt.plot(xs, ys, marker="o")
    plt.title(title)
    plt.xlabel("Known ratings")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def main():
    if not PRODUCTS_JSON.exists():
        raise SystemExit("products.json not found. Run scrape_gouletpens.py first.")

    products = load_products()
    feature_space = FeatureSpace.build(products)

    num_users = 24
    session_length = 6
    seeds = list(range(5))

    rmse_list = []
    rmse_curves = []
    hit_curves = []

    for seed in seeds:
        base_rmse, rmse_curve, hit_curve = run_trial(
            products, feature_space, num_users, session_length, seed
        )
        rmse_list.append(base_rmse)
        rmse_curves.append(rmse_curve)
        hit_curves.append(hit_curve)

    avg_rmse = float(np.mean(rmse_list))
    rmse_curve_avg = aggregate_curves(rmse_curves)
    hit_curve_avg = aggregate_curves(hit_curves)

    plot_curve(
        rmse_curve_avg,
        "RMSE vs Known Ratings (Avg over seeds)",
        "RMSE",
        REPORTS_DIR / "rmse_curve.png",
    )
    plot_curve(
        hit_curve_avg,
        "Top-1 Hit Rate vs Known Ratings (Avg over seeds)",
        "Hit Rate",
        REPORTS_DIR / "hit_rate_curve.png",
    )

    summary_path = REPORTS_DIR / "evaluation_summary.txt"
    summary_lines = [
        "=== PBCF Evaluation (Simulated Users) ===",
        f"Seeds: {len(seeds)} | Users per seed: {num_users} | Session length: {session_length}",
        f"Average RMSE on held-out ratings: {avg_rmse:.3f}",
        "\nRMSE vs. number of known ratings (avg):",
    ]
    for k, val in rmse_curve_avg.items():
        summary_lines.append(f"  Known ratings: {k} -> RMSE: {val:.3f}")
    summary_lines.append("\nTop-1 recommendation hit rate vs. ratings known (avg):")
    for k, val in hit_curve_avg.items():
        summary_lines.append(f"  Known ratings: {k} -> Hit rate: {val:.2f}")

    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n".join(summary_lines))
    print(f"\nSaved plots to {REPORTS_DIR}")


if __name__ == "__main__":
    main()
