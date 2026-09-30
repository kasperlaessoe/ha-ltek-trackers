"""Config, reauth and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ltek_trackers.config_flow import normalize_url
from custom_components.ltek_trackers.const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    SERVER_CUSTOM,
    SERVER_DEVELOPMENT,
    SERVER_PRODUCTION,
    SERVERS,
)

from .conftest import ME, PROD_URL, TOKEN, USER_ID, api_url

DEV_URL = SERVERS[SERVER_DEVELOPMENT]
CUSTOM_URL = "https://timing.example.org"


@pytest.fixture(autouse=True)
def no_setup():
    """Flow tests stop at the entry; setting it up is tested elsewhere."""
    with patch("custom_components.ltek_trackers.async_setup_entry", return_value=True):
        yield


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_production(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(api_url(PROD_URL, "/me"), json=ME)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LTEK Trackers — tester"
    assert result["data"] == {CONF_SERVER: SERVER_PRODUCTION, CONF_URL: PROD_URL, CONF_TOKEN: TOKEN}
    assert result["result"].unique_id == f"{PROD_URL}:{USER_ID}"
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_development_is_a_separate_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(DEV_URL, "/me"), json=ME)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_DEVELOPMENT, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LTEK Trackers — tester (dev)"
    assert result["data"][CONF_URL] == DEV_URL
    assert result["result"].unique_id == f"{DEV_URL}:{USER_ID}"


async def test_custom_url(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(api_url(CUSTOM_URL, "/me"), json=ME)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_CUSTOM, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "custom_url"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://timing.example.org"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_URL: "invalid_url"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{CUSTOM_URL}/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == CUSTOM_URL
    assert result["title"] == "LTEK Trackers — tester (timing.example.org)"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example.org", "https://a.example.org"),
        ("https://a.example.org/base/", "https://a.example.org/base"),
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://127.0.0.1:3000/", "http://127.0.0.1:3000"),
        ("http://a.example.org", None),
        ("ftp://a.example.org", None),
        ("a.example.org", None),
        ("https://", None),
        ("https://a.example.org/?x=1", None),
        ("https://user:pw@a.example.org", None),
    ],
)
def test_normalize_url(raw: str, expected: str | None) -> None:
    assert normalize_url(raw) == expected


async def test_token_format(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: "eyJhbGciOi"}
    )
    assert result["errors"] == {CONF_TOKEN: "invalid_token_format"}
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize("status", [401, 403])
async def test_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    aioclient_mock.get(api_url(PROD_URL, "/me"), status=status)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.parametrize(
    "mock_kwargs", [{"exc": aiohttp.ClientError()}, {"status": 500}, {"json": {"no": "user"}}]
)
async def test_cannot_connect_then_recovers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, mock_kwargs: dict
) -> None:
    aioclient_mock.get(api_url(PROD_URL, "/me"), **mock_kwargs)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(api_url(PROD_URL, "/me"), json=ME)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(PROD_URL, "/me"), json=ME)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_PRODUCTION, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(PROD_URL, "/me"), status=401)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "ltk_revoked"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(api_url(PROD_URL, "/me"), json=ME)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "ltk_newtoken"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "ltk_newtoken"
    assert config_entry.data[CONF_URL] == PROD_URL


async def test_reauth_other_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(PROD_URL, "/me"), json={**ME, "user_id": "someone-else"})
    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "ltk_othertoken"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert config_entry.data[CONF_TOKEN] == TOKEN


async def test_reconfigure_to_development(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(DEV_URL, "/me"), json=ME)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_DEVELOPMENT, CONF_TOKEN: "ltk_devtoken"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {
        CONF_SERVER: SERVER_DEVELOPMENT,
        CONF_URL: DEV_URL,
        CONF_TOKEN: "ltk_devtoken",
    }
    assert config_entry.unique_id == f"{DEV_URL}:{USER_ID}"
    assert config_entry.title == "LTEK Trackers — tester (dev)"


async def test_reconfigure_custom_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.get(api_url(CUSTOM_URL, "/me"), json=ME)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_CUSTOM, CONF_TOKEN: TOKEN}
    )
    assert result["step_id"] == "reconfigure_url"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: CUSTOM_URL}
    )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_URL] == CUSTOM_URL


async def test_reconfigure_onto_existing_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, unique_id=f"{DEV_URL}:{USER_ID}", data={}).add_to_hass(hass)
    aioclient_mock.get(api_url(DEV_URL, "/me"), json=ME)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: SERVER_DEVELOPMENT, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_URL] == PROD_URL
