"""Diagnostics download, stripped of anything that identifies a person or place.

People paste this into public issues, so it keeps only what helps debugging:
the shape of each tracker's state, battery, signal, firmware and fix quality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_TOKEN, CONF_URL

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import LtekTrackersConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_URL, "title", "unique_id", "name", "id", "username", "lat", "lon"}
# Of the position, only fix quality; time, heading, altitude and speed describe
# where someone is and what they are doing.
POSITION_KEEP = ("sats", "h_acc_m")
DROP = {"access"}


def _tracker(tracker: dict[str, Any]) -> dict[str, Any]:
    slim = {k: v for k, v in tracker.items() if k not in DROP}
    position = tracker.get("position")
    if isinstance(position, dict):
        slim["position"] = {k: position[k] for k in POSITION_KEEP if k in position}
    return async_redact_data(slim, TO_REDACT)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LtekTrackersConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(
            {"title": entry.title, "unique_id": entry.unique_id, "data": dict(entry.data)},
            TO_REDACT,
        ),
        "last_update_success": coordinator.last_update_success,
        "trackers": [_tracker(t) for t in coordinator.data.values()],
    }
