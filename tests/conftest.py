"""Shared fixtures. All data here is made up."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ltek_trackers.const import (
    API_PREFIX,
    CONF_SERVER,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    SERVER_PRODUCTION,
    SERVERS,
)

PROD_URL = SERVERS[SERVER_PRODUCTION]
TOKEN = "ltk_testtoken"
USER_ID = "00000000-0000-4000-8000-000000000001"
ME = {"user_id": USER_ID, "username": "tester", "scopes": ["trackers:read"], "fleet": False}

TRACKER_A = "00000000-0000-4000-8000-00000000000a"
TRACKER_B = "00000000-0000-4000-8000-00000000000b"

# Coordinates in the open sea, nowhere in particular.
TRACKERS: list[dict[str, Any]] = [
    {
        "id": TRACKER_A,
        "name": "Test Stick",
        "kind": "trackstick",
        "role": "owner",
        "capabilities": ["config"],
        "online": True,
        "last_seen": "2026-01-01T12:00:00Z",
        "position": {
            "time": "2026-01-01T12:00:00Z",
            "lat": 0.5,
            "lon": -20.25,
            "alt_m": 12,
            "speed_ms": 5.0,
            "heading_deg": 90,
            "h_acc_m": 4,
            "sats": 9,
        },
        "moving": True,
        "battery": {"mv": 3980, "pct": 81},
        "signal": {"rsrp_dbm": -97, "snr_db": 6},
        "firmware": {"app": "1.3.0", "modem": "2.0.2"},
        "config": {"state": "applied"},
        "access": {"via": "owner"},
        "some_future_field": {"ignored": True},
    },
    {
        # A viewer's share: no config, no position yet, nothing optional.
        "id": TRACKER_B,
        "name": "Shared Stick",
        "kind": "trackstick",
        "role": "viewer",
        "capabilities": [],
        "online": False,
        "last_seen": None,
        "position": None,
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def trackers_payload() -> list[dict[str, Any]]:
    return copy.deepcopy(TRACKERS)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="LTEK Trackers — tester",
        unique_id=f"{PROD_URL}:{USER_ID}",
        data={CONF_SERVER: SERVER_PRODUCTION, CONF_URL: PROD_URL, CONF_TOKEN: TOKEN},
    )


def api_url(base: str, path: str = "") -> str:
    return f"{base}{API_PREFIX}{path}"
