from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .codeforces import CodeforcesError, fetch_all_until_known, fetch_user_info, problem_url, to_timezone
from .config import settings
from .db import get_db
from .models import Problem, Submission, User
from .schemas import CalendarDay, DayOut, ProblemOut, StatsOut, SyncOut

app = FastAPI(title="CF Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_or_create_user(db: Session, handle: str) -> User:
    handle = handle.strip()
    user = db.scalar(select(User).where(func.lower(User.cf_handle) == handle.lower()))
    if user:
        return user
    user = User(
        cf_handle=handle,
        timezone=settings.default_timezone,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    return user


def get_problem(db: Session, p: dict) -> Problem | None:
    contest_id = p.get("contestId")
    index = p.get("index")
    if contest_id is None or index is None:
        return None
    return db.scalar(
        select(Problem).where(
            Problem.contest_id == contest_id,
            Problem.problem_index == index,
        )
    )


def upsert_problem(db: Session, p: dict) -> Problem | None:
    existing = get_problem(db, p)
    if existing:
        existing.name = p.get("name", existing.name)
        existing.rating = p.get("rating")
        existing.tags = p.get("tags", [])
        return existing
    if p.get("contestId") is None or p.get("index") is None:
        return None
    problem = Problem(
        contest_id=p["contestId"],
        problem_index=p["index"],
        name=p.get("name", "Unknown"),
        rating=p.get("rating"),
        tags=p.get("tags", []),
    )
    db.add(problem)
    db.flush()
    return problem


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/users/{handle}/sync", response_model=SyncOut)
async def sync_user(handle: str, db: Session = Depends(get_db)):
    try:
        await fetch_user_info(handle)
    except CodeforcesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = get_or_create_user(db, handle)
    known_ids = set(
        db.scalars(
            select(Submission.id)
            .where(Submission.user_id == user.id)
            .order_by(Submission.id.desc())
            .limit(settings.sync_page_size)
        ).all()
    )

    fetched = inserted = new_solved = 0
    async for batch in fetch_all_until_known(user.cf_handle, settings.sync_page_size, known_ids):
        for raw in batch:
            fetched += 1
            if db.get(Submission, raw["id"]):
                continue

            p = raw.get("problem", {})
            problem = upsert_problem(db, p)
            submission = Submission(
                id=raw["id"],
                user_id=user.id,
                problem_id=problem.id if problem else None,
                contest_id=p.get("contestId"),
                problem_index=p.get("index"),
                verdict=raw.get("verdict") or "UNKNOWN",
                programming_language=raw.get("programmingLanguage"),
                submitted_at=to_timezone(raw["creationTimeSeconds"], user.timezone),
                handle=user.cf_handle,
                created_at=datetime.now(timezone.utc),
            )
            db.add(submission)
            inserted += 1
            if raw.get("verdict") == "OK":
                new_solved += 1
        db.commit()

    return SyncOut(handle=user.cf_handle, fetched=fetched, inserted=inserted, new_solved=new_solved)


def solved_rows(db: Session, user: User):
    rows = db.execute(
        select(Submission, Problem)
        .join(Problem, Submission.problem_id == Problem.id)
        .where(Submission.user_id == user.id, Submission.verdict == "OK")
        .order_by(Submission.submitted_at.asc())
    ).all()

    first = {}
    for submission, problem in rows:
        key = (submission.contest_id, submission.problem_index)
        if key not in first:
            first[key] = (submission, problem)
    return list(first.values())


def find_user(db: Session, handle: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.cf_handle) == handle.lower()))
    if not user:
        raise HTTPException(status_code=404, detail="Handle has not been synced yet")
    return user


@app.get("/api/users/{handle}/day/{day}", response_model=DayOut)
def day_view(handle: str, day: date, db: Session = Depends(get_db)):
    user = find_user(db, handle)
    tz = ZoneInfo(user.timezone)
    results = []
    for submission, problem in solved_rows(db, user):
        local = submission.submitted_at.astimezone(tz).date()
        if local == day:
            results.append(
                ProblemOut(
                    contest_id=problem.contest_id,
                    problem_index=problem.problem_index,
                    name=problem.name,
                    rating=problem.rating,
                    tags=problem.tags,
                    solved_at=submission.submitted_at,
                    url=problem_url(problem.contest_id, problem.problem_index),
                )
            )
    return DayOut(date=day, solved_count=len(results), problems=results)


@app.get("/api/users/{handle}/stats", response_model=StatsOut)
def stats(handle: str, db: Session = Depends(get_db)):
    user = find_user(db, handle)
    rows = solved_rows(db, user)
    tz = ZoneInfo(user.timezone)
    by_day: dict[date, list[tuple[Submission, Problem]]] = defaultdict(list)
    for submission, problem in rows:
        by_day[submission.submitted_at.astimezone(tz).date()].append((submission, problem))

    calendar = []
    for day, items in sorted(by_day.items()):
        calendar.append(
            CalendarDay(
                date=day,
                solved_count=len(items),
                ratings=sorted([p.rating for _, p in items if p.rating is not None]),
            )
        )

    max_rating = max((p.rating for _, p in rows if p.rating is not None), default=None)
    today = datetime.now(tz).date()
    streak = 0
    cursor = today
    day_set = set(by_day)
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)

    return StatsOut(
        handle=user.cf_handle,
        total_solved=len(rows),
        current_streak=streak,
        max_rating_solved=max_rating,
        calendar=calendar,
    )
