# CF Tracker

A full-stack Codeforces practice tracker that stores the exact problems you solved, their Codeforces ratings/tags, and the day they were solved.

## Stack

- Backend: FastAPI + SQLAlchemy + psycopg 3
- Database: Supabase PostgreSQL
- Frontend: React + TypeScript + Vite
- Source data: Codeforces API

The Codeforces API currently limits requests to at most one request every two seconds, so the sync implementation sleeps between history pages. See the official API docs: https://codeforces.com/apiHelp/ .

## 1. Create the database

Create a Supabase project. Open **SQL Editor** and run `supabase/schema.sql`.

Supabase provides a full PostgreSQL database. For a persistent FastAPI backend, use the database connection string from the Supabase Dashboard's **Connect** menu. If your hosting environment is IPv4-only, use the Supavisor session pooler connection string instead.

## 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL` to the Supabase PostgreSQL connection string.

Start:

```bash
uvicorn app.main:app --reload --port 8000
```

Check `http://localhost:8000/api/health`.

## 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

## What happens when you sync

1. FastAPI validates the Codeforces handle.
2. It fetches the user's submission history using `user.status`.
3. Problems are upserted by `(contest_id, problem_index)`.
4. Every submission is stored by its unique Codeforces submission ID.
5. Accepted submissions are deduplicated by problem when the UI calculates solved history.
6. The frontend shows exact solved problems and their individual ratings for a selected day.

## API

- `POST /api/users/{handle}/sync`
- `GET /api/users/{handle}/day/{YYYY-MM-DD}`
- `GET /api/users/{handle}/stats`
- `GET /api/health`

## Notes

The backend keeps the raw submissions instead of only storing accepted problems. This means you retain wrong answers, TLEs, compile errors, languages, and timestamps for future features.

The solved date is based on the user's configured timezone, defaulting to `Asia/Kolkata`, so a submission around UTC midnight is assigned to the correct local day.
