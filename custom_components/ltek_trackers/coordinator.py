"""Polls `GET /api/v1/trackers` for the whole account in one request."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, InvalidAuth, TrackersClient
from .const import DOMAIN, LOGGER, SCAN_INTERVAL_S

if TYPE_CHECKING:
    from . import LtekTrackersConfigEntry

type Trackers = dict[str, dict[str, Any]]


def device_identifier(entry: LtekTrackersConfigEntry, tracker_id: str) -> tuple[str, str]:
    """Device key, scoped to the entry's account.

    Two accounts in one HA may both see a shared tracker, and a device belongs
    to one config entry, so each account gets its own device for it.
    """
    return (DOMAIN, f"{entry.unique_id}:{tracker_id}")


class LtekTrackersCoordinator(DataUpdateCoordinator[Trackers]):
    """Latest state of every tracker the token can see, keyed by tracker id."""

    config_entry: LtekTrackersConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: LtekTrackersConfigEntry, client: TrackersClient
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_S),
        )
        self.client = client

    async def _async_update_data(self) -> Trackers:
        try:
            trackers = await self.client.trackers()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ApiError as err:
            raise UpdateFailed(str(err)) from err
        self._sync_devices(trackers)
        return trackers

    def _sync_devices(self, trackers: Trackers) -> None:
        """Drop devices for trackers no longer visible (unshared, expired, released).

        Compared against the registry rather than the previous poll, so a
        tracker that went away while HA was down is also cleaned up. Renames
        made on the website are carried over unless the user renamed it in HA.
        """
        registry = dr.async_get(self.hass)
        wanted = {device_identifier(self.config_entry, tid): t for tid, t in trackers.items()}
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            ours = [i for i in device.identifiers if i[0] == DOMAIN]
            if not ours:
                continue
            tracker = wanted.get(ours[0])
            if tracker is None:
                LOGGER.debug("Removing device %s: tracker no longer visible", device.name)
                registry.async_remove_device(device.id)
                continue
            name = tracker.get("name")
            if isinstance(name, str) and name and name != device.name:
                registry.async_update_device(device.id, name=name)
