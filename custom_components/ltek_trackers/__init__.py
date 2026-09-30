"""The LTEK Trackers integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TrackersClient
from .const import CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import LtekTrackersCoordinator, device_identifier

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
]

type LtekTrackersConfigEntry = ConfigEntry[LtekTrackersCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LtekTrackersConfigEntry) -> bool:
    """Set up LTEK Trackers from a config entry."""
    client = TrackersClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN]
    )
    coordinator = LtekTrackersCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LtekTrackersConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: LtekTrackersConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting a device from the UI only once its tracker is gone."""
    visible = {device_identifier(entry, tid) for tid in entry.runtime_data.data}
    return not any(i in visible for i in device.identifiers if i[0] == DOMAIN)
