from datetime import date, datetime
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field, field_validator


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


class QuestOut(BaseModel):
    id: str
    title: str
    description: str
    progress: int
    target: int
    reward_xp: int
    completed: bool


class ChallengeRule(BaseModel):
    type: Literal["solve_count", "practice_days", "hardest_rating"]
    target: int = Field(ge=1)
    filters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, filters: dict[str, Any]) -> dict[str, Any]:
        allowed = {"min_rating", "max_rating", "tags_any", "tags_all", "contest_ids"}
        unknown = set(filters) - allowed
        if unknown:
            raise ValueError(f"Unknown filter(s): {', '.join(sorted(unknown))}")
        for key in ("min_rating", "max_rating"):
            if key in filters and filters[key] is not None and not isinstance(filters[key], int):
                raise ValueError(f"{key} must be an integer")
        for key in ("tags_any", "tags_all", "contest_ids"):
            if key in filters:
                if not isinstance(filters[key], list):
                    raise ValueError(f"{key} must be an array")
                if key == "contest_ids" and not all(isinstance(v, int) for v in filters[key]):
                    raise ValueError("contest_ids must contain integers")
                if key != "contest_ids" and not all(isinstance(v, str) for v in filters[key]):
                    raise ValueError(f"{key} must contain strings")
        if "min_rating" in filters and "max_rating" in filters and filters["min_rating"] > filters["max_rating"]:
            raise ValueError("min_rating cannot exceed max_rating")
        return filters


class ChallengeCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=500)
    icon: str = Field(default="🏆", max_length=8)
    reward_xp: int = Field(default=100, ge=0, le=5000)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    definition: ChallengeRule
    active: bool = True

    @field_validator("ends_on")
    @classmethod
    def valid_dates(cls, value: Optional[date], info):
        start = info.data.get("starts_on")
        if value is not None and start is not None and value < start:
            raise ValueError("ends_on cannot be earlier than starts_on")
        return value


class ChallengeOut(BaseModel):
    id: str
    slug: str
    title: str
    description: str
    icon: str
    reward_xp: int
    starts_on: Optional[date]
    ends_on: Optional[date]
    definition: dict[str, Any]
    active: bool
    progress: int
    target: int
    completed: bool


class ChallengeAdminOut(BaseModel):
    id: str
    slug: str
    title: str
    description: str
    icon: str
    reward_xp: int
    starts_on: Optional[date]
    ends_on: Optional[date]
    definition: dict[str, Any]
    active: bool
    created_at: datetime


class AchievementOut(BaseModel):
    id: str
    title: str
    description: str
    icon: str
    progress: int
    target: int
    unlocked: bool


class ProfileOut(BaseModel):
    handle: str
    title: str
    level: int
    score: int
    level_xp: int
    next_level_xp: int
    total_solved: int
    current_streak: int
    active_days: int
    max_rating_solved: Optional[int]
    weekly_solved: int


class GameOut(BaseModel):
    profile: ProfileOut
    daily_quests: list[QuestOut]
    weekly_challenges: list[QuestOut]
    custom_challenges: list[ChallengeOut]
    achievements: list[AchievementOut]
    today: date
    weekly_start: date
