"""Setup, entity states, polling, auth failure and tracker removal."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import aiohttp
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.ltek_trackers.const import DOMAIN, SCAN_INTERVAL_S
from custom_components.ltek_trackers.diagnostics import async_get_config_entry_diagnostics

from .conftest import PROD_URL, TOKEN, api_url

TRACKERS_URL = api_url(PROD_URL)


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
    payload: Any,
    **kwargs: Any,
) -> None:
    aioclient_mock.get(TRACKERS_URL, json=payload, **kwargs)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _poll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    **mock_kwargs: Any,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(TRACKERS_URL, **mock_kwargs)
    freezer.tick(timedelta(seconds=SCAN_INTERVAL_S + 1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _devices(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, dr.DeviceEntry]:
    registry = dr.async_get(hass)
    return {d.name: d for d in dr.async_entries_for_config_entry(registry, entry.entry_id)}


async def test_entity_states(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    assert config_entry.state is ConfigEntryState.LOADED
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {TOKEN}"

    location = hass.states.get("device_tracker.test_stick")
    assert location.state == "not_home"
    assert location.attributes["latitude"] == 0.5
    assert location.attributes["longitude"] == -20.25
    assert location.attributes["gps_accuracy"] == 4
    assert location.attributes["battery_level"] == 81
    assert location.attributes["source_type"] == "gps"

    assert hass.states.get("sensor.test_stick_battery").state == "81"
    assert float(hass.states.get("sensor.test_stick_speed").state) == 18.0  # 5 m/s
    assert hass.states.get("sensor.test_stick_speed").attributes["unit_of_measurement"] == "km/h"
    assert hass.states.get("sensor.test_stick_altitude").state == "12"
    assert hass.states.get("sensor.test_stick_signal_strength_rsrp").state == "-97"
    assert hass.states.get("sensor.test_stick_last_seen").state == "2026-01-01T12:00:00+00:00"
    assert hass.states.get("sensor.test_stick_firmware").state == "1.3.0"
    assert hass.states.get("sensor.test_stick_configuration_state").state == "applied"
    assert hass.states.get("binary_sensor.test_stick_moving").state == STATE_ON
    assert hass.states.get("binary_sensor.test_stick_online").state == STATE_ON

    entities = er.async_get(hass)
    for disabled in ("battery_voltage", "satellites", "signal_to_noise_ratio", "modem_firmware"):
        entry = entities.async_get(f"sensor.test_stick_{disabled}")
        assert entry is not None, disabled
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    device = _devices(hass, config_entry)["Test Stick"]
    assert device.manufacturer == "LTEK"
    assert device.model == "trackstick"
    assert device.sw_version == "1.3.0"


async def test_sparse_tracker_does_not_crash(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)

    location = hass.states.get("device_tracker.shared_stick")
    assert location.state == STATE_UNKNOWN
    assert hass.states.get("sensor.shared_stick_battery").state == STATE_UNKNOWN
    assert hass.states.get("sensor.shared_stick_last_seen").state == STATE_UNKNOWN
    assert hass.states.get("binary_sensor.shared_stick_moving").state == STATE_UNKNOWN
    assert hass.states.get("binary_sensor.shared_stick_online").state == STATE_OFF
    # No `config` in a viewer's payload, so no config-state entity.
    assert hass.states.get("sensor.shared_stick_configuration_state") is None


async def test_bad_items_are_skipped(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    trackers_payload[0]["position"] = {"lat": "not a number", "lon": None}
    trackers_payload[0]["battery"] = "flat"
    payload = [*trackers_payload, "junk", {"name": "no id"}]
    await _setup(hass, aioclient_mock, config_entry, payload)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("device_tracker.test_stick").state == STATE_UNKNOWN
    assert hass.states.get("sensor.test_stick_battery").state == STATE_UNKNOWN
    assert len(_devices(hass, config_entry)) == 2


async def test_auth_failure_at_setup_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, aioclient_mock, config_entry, None, status=401)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_server_down_at_setup_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, aioclient_mock, config_entry, None, status=502)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_revoked_token_while_running_starts_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    await _poll(hass, aioclient_mock, freezer, status=401)
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    assert hass.states.get("sensor.test_stick_battery").state == STATE_UNAVAILABLE


async def test_outage_marks_unavailable_then_recovers(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    await _poll(hass, aioclient_mock, freezer, exc=aiohttp.ClientError())
    assert hass.states.get("sensor.test_stick_battery").state == STATE_UNAVAILABLE

    trackers_payload[0]["battery"]["pct"] = 70
    await _poll(hass, aioclient_mock, freezer, json=trackers_payload)
    assert hass.states.get("sensor.test_stick_battery").state == "70"
    assert not hass.config_entries.flow.async_progress()


async def test_tracker_removed_and_added(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    assert set(_devices(hass, config_entry)) == {"Test Stick", "Shared Stick"}

    # The share expired: only A is left.
    await _poll(hass, aioclient_mock, freezer, json=trackers_payload[:1])
    assert set(_devices(hass, config_entry)) == {"Test Stick"}
    assert hass.states.get("device_tracker.shared_stick") is None
    assert er.async_get(hass).async_get("device_tracker.shared_stick") is None

    # Shared again: it comes back without a reload.
    await _poll(hass, aioclient_mock, freezer, json=trackers_payload)
    assert set(_devices(hass, config_entry)) == {"Test Stick", "Shared Stick"}
    assert hass.states.get("binary_sensor.shared_stick_online").state == STATE_OFF


async def test_rename_on_website_updates_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    trackers_payload[0]["name"] = "Renamed Stick"
    await _poll(hass, aioclient_mock, freezer, json=trackers_payload)
    assert "Renamed Stick" in _devices(hass, config_entry)


async def test_manual_device_removal_only_when_gone(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    from custom_components.ltek_trackers import async_remove_config_entry_device

    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    device = _devices(hass, config_entry)["Test Stick"]
    assert not await async_remove_config_entry_device(hass, config_entry, device)

    stale = dr.DeviceEntry(identifiers={(DOMAIN, f"{config_entry.unique_id}:gone")})
    assert await async_remove_config_entry_device(hass, config_entry, stale)


async def test_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redacts_token_and_position(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    trackers_payload: list[dict[str, Any]],
) -> None:
    await _setup(hass, aioclient_mock, config_entry, trackers_payload)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    text = repr(diag)
    assert TOKEN not in text
    assert "-20.25" not in text
    assert diag["entry"]["data"]["token"] == "**REDACTED**"
    assert diag["trackers"][0]["battery"]["pct"] == 81
