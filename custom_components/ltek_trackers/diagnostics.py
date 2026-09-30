"""Diagnostics download, with the token and positions redacted."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_TOKEN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import LtekTrackersConfigEntry

# Positions are personal data and rarely needed to debug; redact them too.
TO_REDACT = {CONF_TOKEN, "lat", "lon", "unique_id"}


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
        "trackers": async_redact_data(list(coordinator.data.values()), TO_REDACT),
    }
