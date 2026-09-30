"""Constants for the LTEK Trackers integration."""

from __future__ import annotations

import logging

DOMAIN = "ltek_trackers"
LOGGER = logging.getLogger(__package__)

CONF_SERVER = "server"
CONF_URL = "url"
CONF_TOKEN = "token"

SERVER_PRODUCTION = "production"
SERVER_DEVELOPMENT = "development"
SERVER_CUSTOM = "custom"

# Public hostnames only. A token is per server: one minted on production does
# not work on development and the other way round.
SERVERS: dict[str, str] = {
    SERVER_PRODUCTION: "https://api.ltek.dk",
    SERVER_DEVELOPMENT: "https://api-dev.cluster.ltek.dk",
}

API_PREFIX = "/api/v1/trackers"

# Personal API tokens start with this, so a pasted JWT or a typo fails in the
# form instead of as a 401 from the server.
TOKEN_PREFIX = "ltk_"

# Plain http is only accepted for a server on the HA host itself.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Sticks report every 60 s moving and 300 s parked; polling faster buys nothing.
SCAN_INTERVAL_S = 30
REQUEST_TIMEOUT_S = 15

MANUFACTURER = "LTEK"
