# Frontend Testing Guide (V2 React)

## Prerequisites

1. Start MongoDB.
2. Start backend:

```bash
cd backend
python -m uvicorn app.main_mongo:app --host localhost --port 8015 --reload
```

3. Start frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Functional Checklist

- Welcome screen accepts player name and starts session.
- Onboarding loads exactly 50 products.
- User can select up to 10 products and not more.
- Continue is enabled only at 10 selections.
- Rating modal submits successfully.
- Round start loads exactly 10 candidates.
- User can lock one pick.
- Result screen shows:
  - Human pick
  - AI pick
  - Round points
  - Post-round metrics
  - AI top candidate list
- Flow advances through 10 rounds.
- Final summary shows final scores and leaderboard.

## API Validation Checklist

- `POST /api/game/start` returns `status: onboarding`.
- `GET /api/game/{id}/onboarding` returns `pool_size: 50`.
- Invalid onboarding payloads return `400`.
- Valid onboarding submit returns `accepted: true`.
- `POST /api/game/{id}/round/start` returns 10 candidates.
- `POST /api/game/{id}/round/{n}/pick` updates cumulative scores.
- `GET /api/game/{id}/status` reflects round progression.
- `GET /api/game/leaderboard` returns completed games only.

## Build/Serve Validation

```bash
cd frontend
npm run build
```

Then open `http://localhost:8015` and verify the React app is served from `frontend/dist`.

