# Decidio Prototype Design Doc

## Goal
Build a prototype that models **sequential preferences** while users assemble a set of products. The system combines a **visual gallery** with **feature-based filtering**, collects **prefix ratings**, and uses a lightweight **prefix-based collaborative filtering** model to recommend the next items.

## User Flow
1. User starts a session.
2. The system shows 2 strong recommendations + 1 wildcard (diversity pick).
3. The user selects an item or marks it as an exception.
4. After a decision moment, the user rates the set so far (1-5) and optionally tags it.
5. The system updates its model and generates the next recommendations.

## UI Concepts (from sponsor notes)
- **Rate the set so far**: prefix ratings are captured after 2-4 selections.
- **Next Pick**: 2 strong + 1 wildcard to control exploration.
- **Exception Mode**: a separate action that downweights the item in the user preference vector.
- **Left brain vs right brain**: a mode toggle switches between image-first exploration and feature-first exploration.

## Data Model
- `Product`: title, vendor, product type, tags, options (nib size), price, image URLs.
- `Session`: sequential state + history.
- `Selection`: product + exception flag.
- `PrefixRating`: rating (1-5) + tags.

## ML Model (Prefix-based CF, Lightweight)
- **Feature space**: vendor, product type, tags, options, normalized price.
- **User vector**: updated after each selection with a decay factor.
- **Exception mode**: applies a lower weight to the selection.
- **Prefix ratings**: adjust a per-session bias term.
- **Recommendation score**: cosine similarity + bias.
- **Coherence**: average pairwise similarity of the current set.

This mirrors prefix-based CF in that the model learns from **prefix ratings** and sequential decisions rather than static single-item ratings.

## Dataset
- Scraped from Goulet Pens (Shopify collection endpoint) with products, images, and options.
- Dataset is stored as `backend/data/products.json` and `backend/data/fountain_pens.csv`.

## API Endpoints
- `POST /api/users`
- `POST /api/sessions`
- `POST /api/sessions/{id}/end`
- `GET /api/products`
- `POST /api/sessions/{id}/select`
- `POST /api/sessions/{id}/rate`
- `GET /api/sessions/{id}/recommendations`
- `GET /api/sessions/{id}/selections`
- `GET /api/debug/pbcf`

## Evaluation (Proof of Learning)
A simulation harness generates synthetic users with latent preferences, creates prefix ratings, and trains the NMF-based PBCF model. We track:
- **RMSE on held-out prefix ratings** (prediction accuracy)
- **Learning curve**: RMSE decreases as more ratings are known
- **Top-1 recommendation hit rate**: accuracy improves with more ratings

Run the evaluation:

```powershell
cd .\Prototype\backend
python .\scripts\evaluate_pbcf.py
```

Artifacts saved to `backend/reports/`:
- `rmse_curve.png`
- `hit_rate_curve.png`
- `evaluation_summary.txt`

## Limitations / Next Iterations
- The current model is a baseline. It can be extended with matrix factorization and global collaborative filtering across users.
- Prefix ratings can be used to train a shared model if multiple user sessions are collected.
- The dataset currently focuses on fountain pens only; lighting can be added later.
