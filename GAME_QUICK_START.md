# Decidio V2 Game Quick Start

## Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main_mongo:app --host localhost --port 8015 --reload
```

## Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Production Build Served by FastAPI

```bash
cd frontend
npm run build
```

Open `http://localhost:8015`.

## Core API Flow

1. `POST /api/game/start`
2. `GET /api/game/{game_id}/onboarding`
3. `POST /api/game/{game_id}/onboarding/submit`
4. `POST /api/game/{game_id}/round/start`
5. `POST /api/game/{game_id}/round/{round_number}/pick`
6. `GET /api/game/{game_id}/status`
7. `GET /api/game/leaderboard`

## Smoke Test

```bash
bash test_game_api.sh
```

