import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://codeforces.com/api"


class CodeforcesError(RuntimeError):
    pass


async def fetch_user_info(handle: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{BASE_URL}/user.info", params={"handles": handle})
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK":
            raise CodeforcesError(data.get("comment", "Codeforces API error"))
        result = data["result"]
        if not result:
            raise CodeforcesError("Codeforces handle not found")
        return result[0]


async def fetch_submissions(handle: str, start: int, count: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{BASE_URL}/user.status",
            params={"handle": handle, "from": start, "count": count},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "OK":
            raise CodeforcesError(data.get("comment", "Codeforces API error"))
        return data["result"]


def to_timezone(timestamp: int, timezone_name: str) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(ZoneInfo(timezone_name))


def problem_url(contest_id: int, index: str) -> str:
    return f"https://codeforces.com/problemset/problem/{contest_id}/{index}"


async def fetch_all_until_known(handle: str, page_size: int, known_ids: set[int]):
    start = 1
    fetched = 0
    while True:
        batch = await fetch_submissions(handle, start, page_size)
        if not batch:
            break
        fetched += len(batch)
        yield batch
        if any(s["id"] in known_ids for s in batch):
            break
        start += page_size
        await asyncio.sleep(2.1)
