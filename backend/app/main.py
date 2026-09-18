from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .codeforces import CodeforcesError, fetch_incremental, problem_url, to_timezone
from .config import settings
from .db import get_db
from .models import Challenge, Problem, Submission, User
from .schemas import (
    AchievementOut,
    CalendarDay,
    ChallengeAdminOut,
    ChallengeCreate,
    ChallengeOut,
    DayOut,
    GameOut,
    ProblemOut,
    ProfileOut,
    QuestOut,
    StatsOut,
    SyncOut,
)

app = FastAPI(title="CF Tracker API", version="3.0.0")

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


def bulk_upsert_batch(db: Session, user: User, batch: list[dict]) -> tuple[int, int]:
    """Insert one Codeforces page with a fixed, small number of DB round-trips."""
    problem_values: dict[tuple[int, str], dict] = {}
    for raw in batch:
        p = raw.get("problem") or {}
        contest_id = p.get("contestId")
        index = p.get("index")
        if contest_id is None or index is None:
            continue
        problem_values[(int(contest_id), str(index))] = {
            "contest_id": int(contest_id),
            "problem_index": str(index),
            "name": p.get("name", "Unknown"),
            "rating": p.get("rating"),
            "tags": p.get("tags", []),
        }

    if problem_values:
        problem_stmt = pg_insert(Problem).values(list(problem_values.values()))
        problem_stmt = problem_stmt.on_conflict_do_update(
            index_elements=[Problem.contest_id, Problem.problem_index],
            set_={
                "name": problem_stmt.excluded.name,
                "rating": problem_stmt.excluded.rating,
                "tags": problem_stmt.excluded.tags,
            },
        )
        db.execute(problem_stmt)

    problem_ids: dict[tuple[int, str], int] = {}
    if problem_values:
        keys = list(problem_values.keys())
        contest_ids = [k[0] for k in keys]
        indexes = [k[1] for k in keys]
        problem_rows = db.execute(
            select(Problem.id, Problem.contest_id, Problem.problem_index)
            .where(
                Problem.contest_id.in_(contest_ids),
                Problem.problem_index.in_(indexes),
            )
        ).all()
        key_set = set(keys)
        for problem_id, contest_id, index in problem_rows:
            key = (int(contest_id), str(index))
            if key in key_set:
                problem_ids[key] = int(problem_id)

    submission_values: list[dict] = []
    for raw in batch:
        p = raw.get("problem") or {}
        contest_id = p.get("contestId")
        index = p.get("index")
        key = (int(contest_id), str(index)) if contest_id is not None and index is not None else None
        submission_values.append({
            "id": int(raw["id"]),
            "user_id": user.id,
            "problem_id": problem_ids.get(key) if key else None,
            "contest_id": contest_id,
            "problem_index": index,
            "verdict": raw.get("verdict") or "UNKNOWN",
            "programming_language": raw.get("programmingLanguage"),
            "submitted_at": to_timezone(raw["creationTimeSeconds"], user.timezone),
            "handle": user.cf_handle,
        })

    if not submission_values:
        return 0, 0

    submission_stmt = pg_insert(Submission).values(submission_values)
    submission_stmt = submission_stmt.on_conflict_do_nothing(index_elements=[Submission.id]).returning(
        Submission.id, Submission.verdict
    )
    inserted_rows = db.execute(submission_stmt).all()
    inserted = len(inserted_rows)
    new_solved = sum(1 for _, verdict in inserted_rows if verdict == "OK")
    return inserted, new_solved


def admin_guard(x_admin_key: str | None = Header(default=None)):
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_key):
        raise HTTPException(status_code=403, detail="Admin access required")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/users/{handle}/sync", response_model=SyncOut)
async def sync_user(handle: str, db: Session = Depends(get_db)):
    user = get_or_create_user(db, handle)

    latest_submission_id = db.scalar(
        select(func.max(Submission.id)).where(Submission.user_id == user.id)
    )
    initial_sync = latest_submission_id is None
    known_submission_id = int(latest_submission_id) if latest_submission_id is not None else None

    cutoff = None
    if initial_sync:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.initial_sync_days)

    fetched = inserted = new_solved = 0

    try:
        async for batch in fetch_incremental(
            user.cf_handle,
            settings.sync_page_size,
            known_submission_id=known_submission_id,
            initial_cutoff_utc=cutoff,
        ):
            fetched += len(batch)
            batch_inserted, batch_solved = bulk_upsert_batch(db, user, batch)
            inserted += batch_inserted
            new_solved += batch_solved
            db.commit()
    except CodeforcesError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return SyncOut(handle=user.cf_handle, fetched=fetched, inserted=inserted, new_solved=new_solved)


def solved_rows(db: Session, user: User):
    """Return one first-accepted row per unique Codeforces problem."""
    return db.execute(
        select(Submission, Problem)
        .join(Problem, Submission.problem_id == Problem.id)
        .where(Submission.user_id == user.id, Submission.verdict == "OK")
        .distinct(Submission.user_id, Submission.contest_id, Submission.problem_index)
        .order_by(
            Submission.user_id,
            Submission.contest_id,
            Submission.problem_index,
            Submission.submitted_at.asc(),
            Submission.id.asc(),
        )
    ).all()


def find_user(db: Session, handle: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.cf_handle) == handle.lower()))
    if not user:
        raise HTTPException(status_code=404, detail="Handle has not been synced yet")
    return user


def group_by_local_day(rows, tz: ZoneInfo):
    by_day: dict[date, list[tuple[Submission, Problem]]] = defaultdict(list)
    for submission, problem in rows:
        by_day[submission.submitted_at.astimezone(tz).date()].append((submission, problem))
    return by_day


def difficulty_xp(rating: int | None) -> int:
    if rating is None:
        return 25
    return max(25, min(200, 25 + round((rating - 700) * 0.09)))


def level_info(score: int) -> tuple[int, int, int]:
    level = max(1, int(math.sqrt(max(score, 0) / 250)) + 1)
    current_floor = 250 * (level - 1) * (level - 1)
    next_floor = 250 * level * level
    return level, score - current_floor, next_floor


def title_for_level(level: int) -> str:
    titles = [
        "Code Cadet", "Logic Runner", "Problem Hunter", "Contest Grinder",
        "Algorithm Adept", "Puzzle Master", "Code Warrior", "Strategy Sage",
        "Algorithm Architect", "Legendary Grinder",
    ]
    return titles[min((level - 1) // 2, len(titles) - 1)]


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def challenge_is_in_window(challenge: Challenge, today: date) -> bool:
    if not challenge.active:
        return False
    if challenge.starts_on and today < challenge.starts_on:
        return False
    if challenge.ends_on and today > challenge.ends_on:
        return False
    return True


def problem_matches_filters(problem: Problem, filters: dict) -> bool:
    rating = problem.rating
    min_rating = filters.get("min_rating")
    max_rating = filters.get("max_rating")
    if min_rating is not None and (rating is None or rating < min_rating):
        return False
    if max_rating is not None and (rating is None or rating > max_rating):
        return False

    tags = set(problem.tags or [])
    tags_any = set(filters.get("tags_any") or [])
    tags_all = set(filters.get("tags_all") or [])
    if tags_any and not tags.intersection(tags_any):
        return False
    if tags_all and not tags_all.issubset(tags):
        return False

    contest_ids = set(filters.get("contest_ids") or [])
    if contest_ids and problem.contest_id not in contest_ids:
        return False
    return True


def challenge_progress(challenge: Challenge, rows, tz: ZoneInfo, today: date) -> tuple[int, int, bool]:
    definition = challenge.definition or {}
    challenge_type = definition.get("type")
    target = int(definition.get("target", 1))
    filters = definition.get("filters") or {}

    matching = []
    for submission, problem in rows:
        local_day = submission.submitted_at.astimezone(tz).date()
        if challenge.starts_on and local_day < challenge.starts_on:
            continue
        if challenge.ends_on and local_day > challenge.ends_on:
            continue
        if problem_matches_filters(problem, filters):
            matching.append((submission, problem))

    if challenge_type == "solve_count":
        progress = len(matching)
    elif challenge_type == "practice_days":
        progress = len({s.submitted_at.astimezone(tz).date() for s, _ in matching})
    elif challenge_type == "hardest_rating":
        progress = max((p.rating or 0 for _, p in matching), default=0)
    else:
        progress = 0

    return min(progress, target), target, progress >= target


def build_challenge_out(challenge: Challenge, rows, tz: ZoneInfo, today: date) -> ChallengeOut:
    progress, target, completed = challenge_progress(challenge, rows, tz, today)
    return ChallengeOut(
        id=str(challenge.id),
        slug=challenge.slug,
        title=challenge.title,
        description=challenge.description,
        icon=challenge.icon,
        reward_xp=challenge.reward_xp,
        starts_on=challenge.starts_on,
        ends_on=challenge.ends_on,
        definition=challenge.definition,
        active=challenge.active,
        progress=progress,
        target=target,
        completed=completed,
    )


def calculate_game_state(rows, tz: ZoneInfo, today: date, all_challenges: list[Challenge]):
    by_day = group_by_local_day(rows, tz)
    total_solved = len(rows)
    active_days = len(by_day)
    max_rating = max((p.rating for _, p in rows if p.rating is not None), default=None)

    current_streak = 0
    cursor = today
    while cursor in by_day:
        current_streak += 1
        cursor -= timedelta(days=1)

    best_streak = 0
    run = 0
    prev_day = None
    for d in sorted(by_day):
        if prev_day is not None and d == prev_day + timedelta(days=1):
            run += 1
        else:
            run = 1
        best_streak = max(best_streak, run)
        prev_day = d

    score = sum(difficulty_xp(problem.rating) for _, problem in rows)
    score += 10 * active_days

    daily_templates = [("warmup", 3, 60), ("climber", 1, 50), ("variety", 3, 70)]
    for items in by_day.values():
        ratings = [p.rating for _, p in items if p.rating is not None]
        bands = {r // 100 for r in ratings}
        if len(items) >= 3:
            score += daily_templates[0][2]
        if any((r or 0) >= 1200 for r in ratings):
            score += daily_templates[1][2]
        if len(bands) >= 3:
            score += daily_templates[2][2]

    by_week: dict[date, list[tuple[Submission, Problem]]] = defaultdict(list)
    for day, items in by_day.items():
        by_week[week_start(day)].extend(items)
    for items in by_week.values():
        ratings = [p.rating for _, p in items if p.rating is not None]
        days_in_week = {s.submitted_at.astimezone(tz).date() for s, _ in items}
        if len(items) >= 10:
            score += 100
        if len(days_in_week) >= 4:
            score += 100
        if sum(r >= 1400 for r in ratings) >= 2:
            score += 120

    sorted_days = sorted(by_day)
    streak_bonus = 0
    run = 0
    prev = None
    for d in sorted_days:
        if prev is not None and d == prev + timedelta(days=1):
            run += 1
        else:
            run = 1
        if run >= 2:
            streak_bonus += 15
        prev = d
    score += streak_bonus

    # Admin-created challenges are also part of the deterministic score.
    # Each challenge contributes its reward exactly once after completion.
    custom_out_all = []
    for challenge in all_challenges:
        _, _, completed = challenge_progress(challenge, rows, tz, today)
        if completed:
            score += challenge.reward_xp

    this_week = week_start(today)
    weekly_items = by_week.get(this_week, [])
    weekly_solved = len(weekly_items)
    weekly_days = {s.submitted_at.astimezone(tz).date() for s, _ in weekly_items}
    weekly_high = sum(1 for _, p in weekly_items if (p.rating or 0) >= 1400)

    today_items = by_day.get(today, [])
    today_ratings = [p.rating for _, p in today_items if p.rating is not None]
    today_bands = {r // 100 for r in today_ratings}

    daily_quests = [
        QuestOut(id="warmup", title="Warm-up Run", description="Solve 3 problems today.", progress=min(len(today_items), 3), target=3, reward_xp=60, completed=len(today_items) >= 3),
        QuestOut(id="climber", title="Climb a Tier", description="Solve one 1200+ rated problem.", progress=min(sum(1 for r in today_ratings if r >= 1200), 1), target=1, reward_xp=50, completed=any(r >= 1200 for r in today_ratings)),
        QuestOut(id="variety", title="Variety Hunter", description="Solve problems from 3 rating bands.", progress=min(len(today_bands), 3), target=3, reward_xp=70, completed=len(today_bands) >= 3),
    ]

    weekly_challenges = [
        QuestOut(id="weekly-grind", title="Weekly Grind", description="Solve 10 problems this week.", progress=min(weekly_solved, 10), target=10, reward_xp=100, completed=weekly_solved >= 10),
        QuestOut(id="consistency", title="Consistency", description="Practice on 4 different days this week.", progress=min(len(weekly_days), 4), target=4, reward_xp=100, completed=len(weekly_days) >= 4),
        QuestOut(id="high-roller", title="High Roller", description="Solve 2 problems rated 1400+ this week.", progress=min(weekly_high, 2), target=2, reward_xp=120, completed=weekly_high >= 2),
    ]

    current_custom = [c for c in all_challenges if challenge_is_in_window(c, today)]
    custom_out = [build_challenge_out(c, rows, tz, today) for c in current_custom]

    achievements = [
        ("first-blood", "First Blood", "Solve your first problem.", "⚔️", total_solved, 1),
        ("ten-pack", "Ten Pack", "Solve 10 problems.", "🔟", total_solved, 10),
        ("fifty-club", "Problem Hunter", "Solve 50 problems.", "🏹", total_solved, 50),
        ("century", "Century", "Solve 100 problems.", "💯", total_solved, 100),
        ("streak-7", "On Fire", "Reach a 7-day streak.", "🔥", best_streak, 7),
        ("rating-1400", "1400 Club", "Solve a 1400+ problem.", "🚀", max_rating or 0, 1400),
        ("rating-1600", "1600 Club", "Solve a 1600+ problem.", "☄️", max_rating or 0, 1600),
    ]
    achievement_out = [AchievementOut(id=a_id, title=title, description=desc, icon=icon, progress=min(progress, target), target=target, unlocked=progress >= target) for a_id, title, desc, icon, progress, target in achievements]

    level, level_xp, next_level_xp = level_info(score)
    profile = ProfileOut(
        handle="",
        title=title_for_level(level),
        level=level,
        score=score,
        level_xp=level_xp,
        next_level_xp=next_level_xp,
        total_solved=total_solved,
        current_streak=current_streak,
        active_days=active_days,
        max_rating_solved=max_rating,
        weekly_solved=weekly_solved,
    )
    return profile, daily_quests, weekly_challenges, custom_out, achievement_out, this_week


@app.post("/api/admin/challenges", response_model=ChallengeAdminOut, dependencies=[Depends(admin_guard)])
def create_challenge(payload: ChallengeCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Challenge).where(Challenge.slug == payload.slug))
    if existing:
        raise HTTPException(status_code=409, detail="A challenge with that slug already exists")
    challenge = Challenge(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        icon=payload.icon,
        reward_xp=payload.reward_xp,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        definition=payload.definition.model_dump(),
        active=payload.active,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return ChallengeAdminOut(
        id=str(challenge.id), slug=challenge.slug, title=challenge.title,
        description=challenge.description, icon=challenge.icon,
        reward_xp=challenge.reward_xp, starts_on=challenge.starts_on,
        ends_on=challenge.ends_on, definition=challenge.definition,
        active=challenge.active, created_at=challenge.created_at,
    )


@app.get("/api/admin/challenges", response_model=list[ChallengeAdminOut], dependencies=[Depends(admin_guard)])
def list_challenges(db: Session = Depends(get_db)):
    challenges = db.scalars(select(Challenge).order_by(Challenge.created_at.desc())).all()
    return [
        ChallengeAdminOut(
            id=str(c.id), slug=c.slug, title=c.title, description=c.description,
            icon=c.icon, reward_xp=c.reward_xp, starts_on=c.starts_on,
            ends_on=c.ends_on, definition=c.definition, active=c.active,
            created_at=c.created_at,
        )
        for c in challenges
    ]


@app.delete("/api/admin/challenges/{challenge_id}", dependencies=[Depends(admin_guard)])
def archive_challenge(challenge_id: str, db: Session = Depends(get_db)):
    challenge = db.get(Challenge, challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    challenge.active = False
    db.commit()
    return {"ok": True}


@app.get("/api/users/{handle}/day/{day}", response_model=DayOut)
def day_view(handle: str, day: date, db: Session = Depends(get_db)):
    user = find_user(db, handle)
    tz = ZoneInfo(user.timezone)
    results = []
    for submission, problem in solved_rows(db, user):
        local = submission.submitted_at.astimezone(tz).date()
        if local == day:
            results.append(ProblemOut(contest_id=problem.contest_id, problem_index=problem.problem_index, name=problem.name, rating=problem.rating, tags=problem.tags, solved_at=submission.submitted_at, url=problem_url(problem.contest_id, problem.problem_index)))
    return DayOut(date=day, solved_count=len(results), problems=results)


@app.get("/api/users/{handle}/stats", response_model=StatsOut)
def stats(handle: str, db: Session = Depends(get_db)):
    user = find_user(db, handle)
    rows = solved_rows(db, user)
    tz = ZoneInfo(user.timezone)
    by_day = group_by_local_day(rows, tz)
    calendar = [CalendarDay(date=day, solved_count=len(items), ratings=sorted([p.rating for _, p in items if p.rating is not None])) for day, items in sorted(by_day.items())]
    max_rating = max((p.rating for _, p in rows if p.rating is not None), default=None)
    today = datetime.now(tz).date()
    streak = 0
    cursor = today
    while cursor in by_day:
        streak += 1
        cursor -= timedelta(days=1)
    return StatsOut(handle=user.cf_handle, total_solved=len(rows), current_streak=streak, max_rating_solved=max_rating, calendar=calendar)


@app.get("/api/users/{handle}/game", response_model=GameOut)
def game(handle: str, db: Session = Depends(get_db)):
    user = find_user(db, handle)
    rows = solved_rows(db, user)
    tz = ZoneInfo(user.timezone)
    today = datetime.now(tz).date()
    all_challenges = db.scalars(select(Challenge).order_by(Challenge.created_at.asc())).all()
    profile, daily_quests, weekly_challenges, custom_challenges, achievements, weekly_start = calculate_game_state(rows, tz, today, all_challenges)
    profile.handle = user.cf_handle
    return GameOut(profile=profile, daily_quests=daily_quests, weekly_challenges=weekly_challenges, custom_challenges=custom_challenges, achievements=achievements, today=today, weekly_start=weekly_start)
