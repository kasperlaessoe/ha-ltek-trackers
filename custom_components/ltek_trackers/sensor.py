"""Battery, motion, radio and housekeeping sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfSpeed,
)
from homeassistant.util import dt as dt_util

from .entity import LtekTrackerEntity, add_trackers_as_they_appear, field, number

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import LtekTrackersConfigEntry
    from .coordinator import LtekTrackersCoordinator

PARALLEL_UPDATES = 0

type Value = float | str | datetime | None


def _number(*path: str) -> Callable[[dict[str, Any] | None], Value]:
    return lambda tracker: number(tracker, *path)


def _text(*path: str) -> Callable[[dict[str, Any] | None], Value]:
    def read(tracker: dict[str, Any] | None) -> Value:
        value = field(tracker, *path)
        return str(value) if isinstance(value, str | int | float) else None

    return read


def _timestamp(*path: str) -> Callable[[dict[str, Any] | None], Value]:
    def read(tracker: dict[str, Any] | None) -> Value:
        value = field(tracker, *path)
        return dt_util.parse_datetime(value) if isinstance(value, str) else None

    return read


@dataclass(frozen=True, kw_only=True)
class LtekSensorDescription(SensorEntityDescription):
    """How to read one value from the latest-state object."""

    value_fn: Callable[[dict[str, Any] | None], Value]
    # Created only when the tracker's payload has this top-level key at the
    # time it is first seen (e.g. `config`, which only managers receive).
    requires: str | None = None


SENSORS: tuple[LtekSensorDescription, ...] = (
    LtekSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number("battery", "pct"),
    ),
    LtekSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        suggested_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_number("battery", "mv"),
    ),
    LtekSensorDescription(
        key="speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number("position", "speed_ms"),
    ),
    LtekSensorDescription(
        key="altitude",
        translation_key="altitude",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number("position", "alt_m"),
    ),
    LtekSensorDescription(
        key="satellites",
        translation_key="satellites",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_number("position", "sats"),
    ),
    LtekSensorDescription(
        key="rsrp",
        translation_key="rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_number("signal", "rsrp_dbm"),
    ),
    LtekSensorDescription(
        key="snr",
        translation_key="snr",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_number("signal", "snr_db"),
    ),
    LtekSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp("last_seen"),
    ),
    LtekSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_text("firmware", "app"),
    ),
    LtekSensorDescription(
        key="modem_firmware",
        translation_key="modem_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_text("firmware", "modem"),
    ),
    LtekSensorDescription(
        key="config_state",
        translation_key="config_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_text("config", "state"),
        requires="config",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LtekTrackersConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors per tracker."""
    coordinator = entry.runtime_data

    def build(tracker_id: str, tracker: dict[str, Any]) -> list[LtekSensor]:
        return [
            LtekSensor(coordinator, tracker_id, d)
            for d in SENSORS
            if d.requires is None or d.requires in tracker
        ]

    add_trackers_as_they_appear(coordinator, entry, async_add_entities, build)


class LtekSensor(LtekTrackerEntity, SensorEntity):
    """A value from the tracker's latest state."""

    entity_description: LtekSensorDescription

    def __init__(
        self,
        coordinator: LtekTrackersCoordinator,
        tracker_id: str,
        description: LtekSensorDescription,
    ) -> None:
        super().__init__(coordinator, tracker_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Value:
        return self.entity_description.value_fn(self.tracker)
