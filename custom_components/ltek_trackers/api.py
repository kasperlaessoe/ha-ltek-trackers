"""Client for the LTEK trackers API (`/api/v1/trackers`)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import API_PREFIX, REQUEST_TIMEOUT_S


class ApiError(Exception):
    """The server could not be reached or answered unexpectedly."""


class InvalidAuth(ApiError):
    """The token was rejected (401) or lacks access (403)."""


@dataclass(frozen=True)
class Account:
    """Who a token belongs to, from `GET /api/v1/trackers/me`."""

    user_id: str
    username: str
    scopes: tuple[str, ...]


class TrackersClient:
    """Thin async client. Owns no session; HA's shared one is passed in."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._token = token

    async def _get(self, path: str) -> Any:
        url = f"{self._base}{API_PREFIX}{path}"
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_S):
                # A redirect would carry the bearer token to wherever it
                # points; the API never redirects, so treat one as an error.
                async with self._session.get(url, headers=headers, allow_redirects=False) as resp:
                    if resp.status in (401, 403):
                        raise InvalidAuth(f"HTTP {resp.status}")
                    if resp.status != 200:
                        raise ApiError(f"HTTP {resp.status} from {path or '/'}")
                    return await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise ApiError(str(err) or type(err).__name__) from err

    async def account(self) -> Account:
        body = await self._get("/me")
        if not isinstance(body, dict) or body.get("user_id") in (None, ""):
            raise ApiError("/me answered without a user_id")
        scopes = body.get("scopes")
        return Account(
            user_id=str(body["user_id"]),
            username=str(body.get("username") or body["user_id"]),
            scopes=tuple(str(s) for s in scopes) if isinstance(scopes, list) else (),
        )

    async def trackers(self) -> dict[str, dict[str, Any]]:
        """Every tracker the token can see, keyed by id, each with its latest state.

        Items that are not objects or carry no id are dropped rather than
        failing the whole refresh.
        """
        body = await self._get("")
        if not isinstance(body, list):
            raise ApiError("/trackers did not answer with a list")
        return {
            str(item["id"]): item
            for item in body
            if isinstance(item, dict) and item.get("id") not in (None, "")
        }
