import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "https://codeforces.com/api"
API_DELAY_SECONDS = 2.1


class CodeforcesError(RuntimeError):
    pass


async def _get(client: httpx.AsyncClient, method: str, params: dict) -> dict:
    response = await client.get(f"{BASE_URL}/{method}", params=params)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "OK":
        raise CodeforcesError(data.get("comment", "Codeforces API error"))
    return data["result"]


async def fetch_user_info(client: httpx.AsyncClient, handle: str) -> dict:
    result = await _get(client, "user.info", {"handles": handle})
    if not result:
        raise CodeforcesError("Codeforces handle not found")
    return result[0]


async def fetch_submissions(
    client: httpx.AsyncClient, handle: str, start: int, count: int
) -> list[dict]:
    return await _get(
        client,
        "user.status",
        {"handle": handle, "from": start, "count": count},
    )


def to_timezone(timestamp: int, timezone_name: str) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
        ZoneInfo(timezone_name)
    )


def problem_url(contest_id: int, index: str) -> str:
    return f"https://codeforces.com/problemset/problem/{contest_id}/{index}"


async def fetch_incremental(
    handle: str,
    page_size: int,
    known_submission_id: int | None,
    initial_cutoff_utc: datetime | None = None,
):
    """Yield new submissions in large pages.

    Existing user: fetch newest submissions until the newest stored submission
    is encountered.

    First sync: fetch only submissions newer than initial_cutoff_utc.

    Codeforces rate-limits API calls to at most one every two seconds, so we
    only sleep when another page is actually needed.
    """
    start = 1
    first_request = True

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            if not first_request:
                await asyncio.sleep(API_DELAY_SECONDS)

            batch = await fetch_submissions(client, handle, start, page_size)
            first_request = False

            if not batch:
                break

            stop = False
            filtered: list[dict] = []

            for submission in batch:
                submission_id = int(submission["id"])

                # user.status is newest -> oldest, so once we hit the newest
                # stored submission, everything after it is already known.
                if known_submission_id is not None and submission_id <= known_submission_id:
                    stop = True
                    break

                created_at = datetime.fromtimestamp(
                    submission["creationTimeSeconds"], tz=timezone.utc
                )

                if initial_cutoff_utc is not None and created_at < initial_cutoff_utc:
                    stop = True
                    break

                filtered.append(submission)

            if filtered:
                yield filtered

            if stop or len(batch) < page_size:
                break

            start += page_size
