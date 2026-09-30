"""Config flow for LTEK Trackers: pick a server, paste a personal API token."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import Account, ApiError, InvalidAuth, TrackersClient
from .const import (
    CONF_SERVER,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    LOCAL_HOSTS,
    LOGGER,
    SERVER_CUSTOM,
    SERVER_DEVELOPMENT,
    SERVER_PRODUCTION,
    SERVERS,
    TOKEN_PREFIX,
)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))

SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERVER, default=SERVER_PRODUCTION): SelectSelector(
            SelectSelectorConfig(
                options=[SERVER_PRODUCTION, SERVER_DEVELOPMENT, SERVER_CUSTOM],
                translation_key=CONF_SERVER,
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
    }
)
URL_SCHEMA = vol.Schema({vol.Required(CONF_URL): URL_SELECTOR})
TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR})


def normalize_url(raw: str) -> str | None:
    """Return a canonical base URL, or None if it is not acceptable.

    https is required unless the host is the HA machine itself.
    """
    try:
        parts = urlsplit(raw.strip())
        host = parts.hostname
    except ValueError:
        return None
    if not host or parts.query or parts.fragment or parts.username or parts.password:
        return None
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOCAL_HOSTS):
        return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")
    return None


def entry_title(server: str, url: str, account: Account) -> str:
    """Title shown on the integration card."""
    title = f"LTEK Trackers — {account.username}"
    if server == SERVER_DEVELOPMENT:
        return f"{title} (dev)"
    if server == SERVER_CUSTOM:
        return f"{title} ({urlsplit(url).netloc})"
    return title


def entry_unique_id(url: str, account: Account) -> str:
    """One entry per account per server: prod and dev are two entries."""
    return f"{url}:{account.user_id}"


class LtekTrackersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LTEK Trackers."""

    VERSION = 1

    def __init__(self) -> None:
        self._server = SERVER_PRODUCTION
        self._token = ""

    async def _validate(self, url: str, token: str) -> tuple[Account | None, dict[str, str]]:
        if not token.startswith(TOKEN_PREFIX):
            return None, {CONF_TOKEN: "invalid_token_format"}
        client = TrackersClient(async_get_clientsession(self.hass), url, token)
        try:
            return await client.account(), {}
        except InvalidAuth:
            return None, {"base": "invalid_auth"}
        except ApiError as err:
            LOGGER.debug("Cannot reach %s: %s", url, err)
            return None, {"base": "cannot_connect"}

    async def _finish(self, url: str, token: str) -> tuple[ConfigFlowResult | None, dict[str, str]]:
        """Validate and create (or, when reconfiguring, update) the entry."""
        account, errors = await self._validate(url, token)
        if account is None:
            return None, errors
        data = {CONF_SERVER: self._server, CONF_URL: url, CONF_TOKEN: token}
        unique_id = entry_unique_id(url, account)
        title = entry_title(self._server, url, account)

        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            # Switching server is the point of reconfigure, so the account may
            # change; it may not collide with another entry that already has it.
            if unique_id != entry.unique_id:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
            return (
                self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, title=title, data=data
                ),
                {},
            )

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title, data=data), {}

    async def _server_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._server = user_input[CONF_SERVER]
            self._token = user_input[CONF_TOKEN].strip()
            if self._server == SERVER_CUSTOM:
                if not self._token.startswith(TOKEN_PREFIX):
                    errors[CONF_TOKEN] = "invalid_token_format"
                else:
                    if step_id == "reconfigure":
                        return await self.async_step_reconfigure_url()
                    return await self.async_step_custom_url()
            else:
                result, errors = await self._finish(SERVERS[self._server], self._token)
                if result is not None:
                    return result

        schema = SERVER_SCHEMA
        if user_input is None and self.source == SOURCE_RECONFIGURE:
            current = self._get_reconfigure_entry().data.get(CONF_SERVER, SERVER_PRODUCTION)
            schema = self.add_suggested_values_to_schema(SERVER_SCHEMA, {CONF_SERVER: current})
        elif user_input is not None:
            schema = self.add_suggested_values_to_schema(
                SERVER_SCHEMA, {CONF_SERVER: user_input[CONF_SERVER]}
            )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def _url_step(self, step_id: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            if url is None:
                errors[CONF_URL] = "invalid_url"
            else:
                result, errors = await self._finish(url, self._token)
                if result is not None:
                    return result
        suggested = user_input
        if suggested is None and self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            if entry.data.get(CONF_SERVER) == SERVER_CUSTOM:
                suggested = {CONF_URL: entry.data.get(CONF_URL, "")}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, suggested or {}),
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose the server and paste a token."""
        return await self._server_step("user", user_input)

    async def async_step_custom_url(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the base URL of a self-hosted server."""
        return await self._url_step("custom_url", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Switch server or token on an existing entry."""
        return await self._server_step("reconfigure", user_input)

    async def async_step_reconfigure_url(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Custom URL while reconfiguring."""
        return await self._url_step("reconfigure_url", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The token stopped working: ask for a new one for the same account."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Paste a replacement token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            account, errors = await self._validate(entry.data[CONF_URL], token)
            if account is not None:
                await self.async_set_unique_id(entry_unique_id(entry.data[CONF_URL], account))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )
