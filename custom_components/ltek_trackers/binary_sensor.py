"""Moving and online as binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import LtekTrackerEntity, add_trackers_as_they_appear, field

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import LtekTrackersConfigEntry
    from .coordinator import LtekTrackersCoordinator

PARALLEL_UPDATES = 0


def _flag(*path: str) -> Callable[[dict[str, Any] | None], bool | None]:
    def read(tracker: dict[str, Any] | None) -> bool | None:
        value = field(tracker, *path)
        return value if isinstance(value, bool) else None

    return read


@dataclass(frozen=True, kw_only=True)
class LtekBinarySensorDescription(BinarySensorEntityDescription):
    """How to read one flag from the latest-state object."""

    value_fn: Callable[[dict[str, Any] | None], bool | None]


BINARY_SENSORS: tuple[LtekBinarySensorDescription, ...] = (
    LtekBinarySensorDescription(
        key="moving",
        translation_key="moving",
        device_class=BinarySensorDeviceClass.MOVING,
        value_fn=_flag("moving"),
    ),
    LtekBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=_flag("online"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LtekTrackersConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors per tracker."""
    coordinator = entry.runtime_data

    def build(tracker_id: str, _tracker: dict[str, Any]) -> list[LtekBinarySensor]:
        return [LtekBinarySensor(coordinator, tracker_id, d) for d in BINARY_SENSORS]

    add_trackers_as_they_appear(coordinator, entry, async_add_entities, build)


class LtekBinarySensor(LtekTrackerEntity, BinarySensorEntity):
    """A flag from the tracker's latest state."""

    entity_description: LtekBinarySensorDescription

    def __init__(
        self,
        coordinator: LtekTrackersCoordinator,
        tracker_id: str,
        description: LtekBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, tracker_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.tracker)
