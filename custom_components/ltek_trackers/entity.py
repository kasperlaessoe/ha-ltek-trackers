"""Shared entity base: one HA device per tracker."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MANUFACTURER
from .coordinator import LtekTrackersCoordinator, device_identifier

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import LtekTrackersConfigEntry


def field(tracker: dict[str, Any] | None, *path: str) -> Any:
    """Walk nested keys; any missing or non-object step yields None."""
    value: Any = tracker
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def number(tracker: dict[str, Any] | None, *path: str) -> float | None:
    """A numeric field, or None when missing or not a number."""
    value = field(tracker, *path)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    return value


class LtekTrackerEntity(CoordinatorEntity[LtekTrackersCoordinator]):
    """An entity belonging to one tracker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LtekTrackersCoordinator, tracker_id: str, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.tracker_id = tracker_id
        self._attr_unique_id = f"{entry.unique_id}:{tracker_id}:{key}"
        tracker = coordinator.data.get(tracker_id, {})
        firmware = field(tracker, "firmware", "app")
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(entry, tracker_id)},
            name=field(tracker, "name") or tracker_id,
            manufacturer=MANUFACTURER,
            model=field(tracker, "kind"),
            sw_version=str(firmware) if firmware is not None else None,
        )

    @property
    def tracker(self) -> dict[str, Any] | None:
        """This tracker's latest state, or None once it is no longer visible."""
        return self.coordinator.data.get(self.tracker_id)

    @property
    def available(self) -> bool:
        return super().available and self.tracker is not None


def add_trackers_as_they_appear(
    coordinator: LtekTrackersCoordinator,
    entry: LtekTrackersConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build: Callable[[str, dict[str, Any]], Iterable[Entity]],
) -> None:
    """Add entities for current trackers now and for new ones on later polls."""
    known: set[str] = set()

    @callback
    def add_new() -> None:
        # Forget trackers whose device was removed, so they are re-added if
        # they come back; ones still in their grace period keep their entities.
        known.intersection_update(coordinator.tracked | set(coordinator.data))
        new = set(coordinator.data) - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            entity for tid in sorted(new) for entity in build(tid, coordinator.data[tid])
        )

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))
