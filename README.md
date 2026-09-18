# CF//QUEST

A gamified Codeforces practice tracker built with FastAPI, PostgreSQL/Supabase, React and TypeScript.

## What it tracks

- Exact problem rating, name, tags and solve time
- Accepted and non-accepted submissions
- Incremental Codeforces syncing (newest-first, stop at known submission)
- A 30-day bounded bootstrap sync for a first connection
- Daily quests
- Weekly challenges
- XP, score and levels derived from your real solved history
- Streaks and active practice days
- Achievement badges
- Daily problem list and rating breakdown data

## Stack

- Backend: FastAPI + SQLAlchemy + Psycopg 3
- Database: Supabase PostgreSQL
- Frontend: React + TypeScript + Vite
- Source: Codeforces public API

## Setup

### 1. Supabase

Run `supabase/schema.sql` in your Supabase SQL editor. If you already ran the schema from an earlier version of CF Tracker, you do not need a new table migration for the game layer: all game state is derived from your existing submission data.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `DATABASE_URL` to your Supabase PostgreSQL connection string. Use the Psycopg 3 SQLAlchemy format:

```env
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=http://localhost:5173
DEFAULT_TIMEZONE=Asia/Kolkata
SYNC_PAGE_SIZE=1000
INITIAL_SYNC_DAYS=30
```

Run:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Use `VITE_API_URL=http://localhost:8000` locally.

## Game rules

### Solve XP

Every distinct problem solved for the first time awards difficulty-based XP. Unrated problems give a small fixed amount. Re-solving the same problem does not create duplicate solve XP.

### Daily quests

- Warm-up Run: solve 3 problems
- Climb a Tier: solve one 1200+ problem
- Variety Hunter: solve problems from 3 rating bands

### Weekly challenges

- Weekly Grind: 10 problems
- Consistency: practice on 4 different days
- High Roller: solve 2 problems rated 1400+

Quest and challenge rewards are computed historically from your recorded solves, so the score stays reproducible without extra state tables.


## Backend performance

The sync path is optimized for Supabase/PostgreSQL: Codeforces pages are fetched in large batches, problems are bulk-upserted, submissions are bulk-inserted with `ON CONFLICT DO NOTHING`, and game/stat endpoints let PostgreSQL deduplicate repeated accepted submissions.

If you already have the database schema, add this index once in the Supabase SQL editor:

```sql
create index if not exists submissions_user_id_desc_idx
  on public.submissions(user_id, id desc);
```

## Admin-authored challenges

The game now supports rule-based challenges created from a structured JSON document.

1. Run `supabase/challenge_migration.sql` once in the Supabase SQL editor.
2. Add `ADMIN_KEY=<long-random-secret>` to `backend/.env`.
3. Open the web app and choose **Admin**.
4. Enter the same key. The key is sent as `X-Admin-Key` to the FastAPI backend.
5. Paste a challenge JSON and publish it.

Example:

```json
{
  "slug": "dp-hunter",
  "title": "DP Hunter",
  "description": "Solve 5 dynamic programming problems rated 1200 or higher.",
  "icon": "🧠",
  "reward_xp": 250,
  "starts_on": "2026-09-17",
  "ends_on": "2026-09-23",
  "definition": {
    "type": "solve_count",
    "target": 5,
    "filters": {
      "min_rating": 1200,
      "tags_any": ["dp"]
    }
  },
  "active": true
}
```

Supported rule types:

- `solve_count`: count unique accepted problems matching the filters.
- `practice_days`: count distinct local calendar days with a matching accepted problem.
- `hardest_rating`: highest solved rating matching the filters. The `target` becomes the required rating.

Supported filters are `min_rating`, `max_rating`, `tags_any`, `tags_all`, and `contest_ids`.

For a deployed app, replace the simple admin key with proper authentication before opening the admin console to untrusted users.
