from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    id: str
    cf_handle: str
    timezone: str


class ProblemOut(BaseModel):
    contest_id: int
    problem_index: str
    name: str
    rating: Optional[int] = None
    tags: list[str]
    solved_at: datetime
    url: str


class DayOut(BaseModel):
    date: date
    solved_count: int
    problems: list[ProblemOut]


class CalendarDay(BaseModel):
    date: date
    solved_count: int
    ratings: list[int]


class StatsOut(BaseModel):
    handle: str
    total_solved: int
    current_streak: int
    max_rating_solved: Optional[int]
    calendar: list[CalendarDay]


class SyncOut(BaseModel):
    handle: str
    fetched: int
    inserted: int
    new_solved: int
