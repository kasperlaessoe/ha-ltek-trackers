"""Tracker position as a GPS device_tracker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity

from .entity import LtekTrackerEntity, add_trackers_as_they_appear, number

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import LtekTrackersConfigEntry
    from .coordinator import LtekTrackersCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LtekTrackersConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one location entity per tracker."""
    coordinator = entry.runtime_data

    def build(tracker_id: str, _tracker: dict[str, Any]) -> list[LtekTrackerLocation]:
        return [LtekTrackerLocation(coordinator, tracker_id)]

    add_trackers_as_they_appear(coordinator, entry, async_add_entities, build)


class LtekTrackerLocation(LtekTrackerEntity, TrackerEntity):
    """Where the tracker is; works with zones, person entities and the map card."""

    _attr_name = None
    _attr_translation_key = "location"

    def __init__(self, coordinator: LtekTrackersCoordinator, tracker_id: str) -> None:
        super().__init__(coordinator, tracker_id, "location")

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return number(self.tracker, "position", "lat")

    @property
    def longitude(self) -> float | None:
        return number(self.tracker, "position", "lon")

    @property
    def location_accuracy(self) -> float:
        # HA wants a number; 0 means "unknown" to the zone logic.
        return number(self.tracker, "position", "h_acc_m") or 0

    @property
    def battery_level(self) -> int | None:
        pct = number(self.tracker, "battery", "pct")
        return round(pct) if pct is not None else None
