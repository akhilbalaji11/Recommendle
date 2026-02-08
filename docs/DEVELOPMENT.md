# Development Guide

Detailed technical reference for contributors and developers. For a quick overview and setup instructions, see the root [README](../README.md).

---

## Design Philosophy

### Goal

Model **sequential preferences** as users assemble a set of products. The system collects **prefix ratings** (rate the set so far, not individual items) and uses a lightweight **prefix-based collaborative filtering** model to predict and recommend the next items.

### UI Concepts

- **Rate the set so far**: prefix ratings are captured after onboarding, not per-item.
- **Left brain vs. right brain**: a mode toggle switches between image-first exploration and feature-first exploration.
- **Diversity**: onboarding and round candidates mix top-likelihood picks with wildcard/decoy items.

### Visual Style

- Clean, responsive layouts with a restrained color palette.
- Dark-mode-friendly deep navy backgrounds with vibrant accent gradients.
- Typography: modern sans-serif stack.

---

## MongoDB Data Model

### Products Collection

```javascript
{
  "_id": ObjectId("..."),
  "source_id": "goulet-pens-123",
  "title": "TWSBI Eco",
  "vendor": "TWSBI",
  "product_type": "Fountain Pen",
  "price_min": 34.00,
  "price_max": 38.00,
  "currency": "USD",
  "tags": ["demonstrator", "piston-fill"],
  "options": {
    "color": ["Clear", "Blue", "Carmine"],
    "nib": ["EF", "F", "M", "B", "Stub"]
  },
  "description": "...",
  "url": "https://...",
  "images": [
    { "url": "https://...", "alt": "TWSBI Eco front view", "position": 0 }
  ],
  "created_at": ISODate("...")
}
```

### Users Collection

```javascript
{
  "_id": ObjectId("..."),
  "name": "John Doe",
  "sessions": [ObjectId("...")],
  "created_at": ISODate("...")
}
```

### Sessions Collection

```javascript
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "state": {
    "user_vec": [0.1, 0.2, ...],
    "bias": 0.5,
    "count": 3
  },
  "selections": [ObjectId("...")],
  "prefix_ratings": [ObjectId("...")],
  "created_at": ISODate("...")
}
```

### Selections Collection

```javascript
{
  "_id": ObjectId("..."),
  "session_id": ObjectId("..."),
  "product_id": ObjectId("..."),
  "is_exception": false,
  "created_at": ISODate("...")
}
```

### Prefix Ratings Collection

```javascript
{
  "_id": ObjectId("..."),
  "session_id": ObjectId("..."),
  "rating": 4,
  "tags": ["demonstrator", "piston-fill"],
  "created_at": ISODate("...")
}
```

### Indexes

Created automatically by the migration/load scripts:

- `products.source_id` (unique)
- `products.title`
- `products.vendor`
- `users.name`

Additional indexes to add for performance:

```javascript
db.products.createIndex({ "price_min": 1 })
db.products.createIndex({ "tags": 1 })
db.sessions.createIndex({ "user_id": 1 })
db.selections.createIndex({ "session_id": 1 })
```

---

## Legacy API Endpoints (Recommendation Mode)

These endpoints power the original recommendation UI (non-game mode):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/products` | List products (with filtering) |
| `GET` | `/api/products/{id}` | Get a specific product |
| `POST` | `/api/users` | Create a user |
| `POST` | `/api/sessions` | Create a session |
| `POST` | `/api/sessions/{id}/select` | Select a product |
| `POST` | `/api/sessions/{id}/rate` | Rate the current prefix |
| `GET` | `/api/sessions/{id}/recommendations` | Get recommendations |
| `GET` | `/api/sessions/{id}/selections` | Get selections |
| `GET` | `/api/debug/pbcf` | View PBCF model statistics |

---

## Evaluation (Proof of Learning)

A simulation harness generates synthetic users with latent preferences, creates prefix ratings, and trains the NMF-based PBCF model.

### Metrics Tracked

- **RMSE on held-out prefix ratings** — prediction accuracy.
- **Learning curve** — RMSE decreases as more ratings are known.
- **Top-1 recommendation hit rate** — accuracy improves with more ratings.

### Run the Evaluation

```bash
cd backend
python -m scripts.evaluate_pbcf
```

Artifacts are saved to `backend/reports/`:

- `rmse_curve.png`
- `hit_rate_curve.png`
- `evaluation_summary.txt`

---

## Testing

### API Smoke Test

```bash
bash test_game_api.sh
```

### Frontend Functional Checklist

- [ ] Welcome screen accepts player name and starts session.
- [ ] Onboarding loads exactly 50 products.
- [ ] User can select up to 10 products (not more).
- [ ] Continue button is enabled only at 10 selections.
- [ ] Rating modal submits successfully.
- [ ] Round start loads exactly 10 candidates.
- [ ] User can lock one pick per round.
- [ ] Result screen shows human pick, AI pick, round points, post-round metrics, and AI top candidate list.
- [ ] Flow advances through all 10 rounds.
- [ ] Final summary shows final scores and leaderboard.

### API Validation Checklist

- [ ] `POST /api/game/start` returns `status: onboarding`.
- [ ] `GET /api/game/{id}/onboarding` returns `pool_size: 50`.
- [ ] Invalid onboarding payloads return `400`.
- [ ] Valid onboarding submit returns `accepted: true`.
- [ ] `POST /api/game/{id}/round/start` returns 10 candidates.
- [ ] `POST /api/game/{id}/round/{n}/pick` updates cumulative scores.
- [ ] `GET /api/game/{id}/status` reflects round progression.
- [ ] `GET /api/game/leaderboard` returns completed games only.

### Build Verification

```bash
cd frontend && npm run build
```

Then open `http://localhost:8015` and verify the React app is served from `frontend/dist`.

---

## Troubleshooting

### MongoDB Connection Failed

```
pymongo.errors.ServerSelectionTimeoutError: No servers found
```

Make sure MongoDB is running:

```bash
mongosh --eval "db.adminCommand('ping')"
```

If not running, start it:

- **Windows**: Run as a service or `mongod --dbpath C:\data\db`
- **Mac**: `brew services start mongodb-community`
- **Linux**: `mongod`

### Resetting the Database

Drop all collections and reload:

```javascript
use decidio
db.products.drop()
db.users.drop()
db.sessions.drop()
db.selections.drop()
db.prefix_ratings.drop()
```

Then re-run `python -m scripts.load_db`.

### SQLite Fallback

The original SQLite backend is still available:

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8015
```

The SQLite database is at `data/decidio.db`.

---

## Limitations & Future Work

- The current model is a baseline. It can be extended with matrix factorization and global collaborative filtering across users.
- Prefix ratings can be used to train a shared model if multiple user sessions are collected.
- The dataset currently focuses on fountain pens only; other product categories can be added.
- Exception mode (downweighting a selection in the user preference vector) is modeled but not yet surfaced in the game UI.
