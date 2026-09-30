"""Polls `GET /api/v1/trackers` for the whole account in one request."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, InvalidAuth, TrackersClient
from .const import DOMAIN, LOGGER, MISSING_POLLS_BEFORE_REMOVAL, SCAN_INTERVAL_S

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
        # Tracker id -> consecutive polls it has been absent from.
        self._missing: dict[str, int] = {}
        self._warned_empty = False
        # Trackers that still have a device: visible now, or absent but not
        # yet removed. Platforms keep their entities for exactly these.
        self.tracked: set[str] = set()

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

        A tracker must be missing from `MISSING_POLLS_BEFORE_REMOVAL`
        consecutive answers before its device goes, so one odd response does
        not wipe entity customisations. An empty list removes nothing: it is
        far more likely a server-side hiccup than every share ending at once.
        Compared against the registry rather than the previous poll, so a
        tracker that went away while HA was down is also cleaned up. Renames
        made on the website are carried over.
        """
        if not trackers:
            if not self._warned_empty:
                LOGGER.warning("The server returned no trackers; keeping existing devices")
                self._warned_empty = True
            return
        self._warned_empty = False

        registry = dr.async_get(self.hass)
        entry = self.config_entry
        prefix = f"{entry.unique_id}:"
        missing: dict[str, int] = {}
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            ours = [i[1] for i in device.identifiers if i[0] == DOMAIN]
            if not ours:
                continue
            tracker_id = ours[0].removeprefix(prefix)
            tracker = trackers.get(tracker_id)
            if tracker is None:
                misses = self._missing.get(tracker_id, 0) + 1
                if misses < MISSING_POLLS_BEFORE_REMOVAL:
                    missing[tracker_id] = misses
                    continue
                LOGGER.debug("Removing device %s: tracker no longer visible", device.name)
                registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
                continue
            name = tracker.get("name")
            if isinstance(name, str) and name and name != device.name:
                registry.async_update_device(device.id, name=name)
        self._missing = missing
        self.tracked = set(trackers) | set(missing)
