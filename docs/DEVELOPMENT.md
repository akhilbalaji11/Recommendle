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

## Evaluation (AI Performance Analysis)

The evaluation script analyzes **real completed game data** from MongoDB to measure how well the AI predicts player choices.

### Prerequisites

- MongoDB running with at least one completed game in the database.
- Play a full game at `http://localhost:5173` first.

### Run the Evaluation

```bash
cd backend
python -m scripts.evaluate_pbcf
```

### Reports Generated

Artifacts are saved to `backend/reports/` (git-ignored, generated locally):

| File | Description |
|------|-------------|
| `evaluation_summary.txt` | Full text report with all metrics |
| `evaluation_data.json` | Raw metrics as JSON for programmatic use |
| `ai_accuracy_by_round.png` | Bar chart: does the AI improve over 10 rounds? |
| `score_distribution.png` | Human vs AI scores per game + delta histogram |
| `learning_metrics.png` | Coherence & predicted prefix rating evolution |

### Metrics Tracked

- **Overall AI accuracy** — what percentage of rounds does the AI correctly predict the human's pick?
- **AI accuracy by round** — the core learning curve: does the AI get better as it learns more about you?
- **Game outcomes** — human wins vs AI wins vs ties, average scores.
- **AI rank analysis** — when the AI is wrong, where did your pick rank in its candidate list?
- **Model learning metrics** — how coherence score and predicted prefix rating evolve across rounds.

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
- [ ] Hidden Patterns Emerging section appears when hidden preferences are detected (typically round 3+).
- [ ] Flow advances through all 10 rounds.
- [ ] Final summary shows final scores and leaderboard.
- [ ] Hidden Gems panel shows detected latent features, narrative explanation, and gem product recommendations.

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

## Hidden Preference Detection

The hidden preference system identifies features the user accumulated incidentally (via co-occurrence) rather than intentionally.

### Algorithm

1. **Build a selection-frequency vector** — for each feature dimension, count how many of the user's selected products activate that dimension, then normalize to 0–1.
2. **Normalize the user vector** — scale the model's learned `user_vec` to 0–1.
3. **Compute latency score** — `latency[i] = normalized_weight[i] − frequency[i]`. High latency means the model learned to value a feature the user didn't directly target.
4. **Filter** — only features with `weight ≥ 0.15`, `latency ≥ 0.10`, and `≥ 3` selections qualify. Price dimensions are excluded.
5. **Hidden Gem products** — a masked user vector (zeroing out non-hidden dimensions) is used to score all products; those not already selected are returned as gem recommendations.

### Thresholds (tunable in `prefix_cf.py`)

| Constant | Default | Purpose |
|----------|---------|--------|
| `HIDDEN_MIN_WEIGHT` | 0.15 | Minimum normalized weight to consider a feature |
| `HIDDEN_MIN_LATENCY` | 0.10 | Minimum gap between weight and selection frequency |
| `HIDDEN_MIN_SELECTIONS` | 3 | Minimum selections before detection activates |

### Files Involved

| File | Role |
|------|------|
| `backend/app/ml/prefix_cf.py` | `detect_hidden_preferences()`, `get_hidden_gem_products()` |
| `backend/app/services/game_service.py` | Integration in `submit_pick()` (progressive hints) and `get_game_summary()` (full reveal) |
| `backend/app/schemas_game.py` | Response schemas for hidden preference data |
| `frontend/src/components/RoundResultPanel.jsx` | "Hidden Patterns Emerging" per-round UI |
| `frontend/src/components/FinalSummary.jsx` | "Hidden Gems" end-of-game panel |
| `frontend/src/styles.css` | `.feature-tag.hidden`, `.hidden-gems-panel` styles |

---

## Limitations & Future Work

- The current model is a baseline. It can be extended with matrix factorization and global collaborative filtering across users.
- Prefix ratings can be used to train a shared model if multiple user sessions are collected.
- The dataset currently focuses on fountain pens only; other product categories can be added.
- Exception mode (downweighting a selection in the user preference vector) is modeled but not yet surfaced in the game UI.
- Hidden preference thresholds are static; they could be adaptive based on the number of rounds played or the variance in the user vector.
