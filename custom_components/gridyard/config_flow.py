"""Config flow for the gridyard integration."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import probatio
from gridyard import (
    ApiUnsupported,
    CannotConnect,
    Catalog,
    DeviceInfo,
    GridyardClient,
    GridyardError,
    InvalidAuth,
)
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import BooleanSelector

from .const import (
    CONF_METER_KEY,
    CONF_PROFILE,
    CONF_SETUP_CODE,
    CONF_UPDATE_CHECK,
    DOMAIN,
)
from .coordinator import GridyardConfigEntry
from .settings import (
    METER_KEY_SELECTOR,
    meter_key_valid,
    normalize_meter_key,
    profile_encrypted,
    profile_in_catalog,
    profile_schema,
    profile_selector,
    send_settings,
    settings_error,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): str})
STEP_SETUP_CODE_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_SETUP_CODE): str})
STEP_METER_KEY_DATA_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_METER_KEY): METER_KEY_SELECTOR}
)
# 12 characters Crockford Base32, as on the label of the device.
SETUP_CODE_PATTERN = re.compile(r"[0-9ABCDEFGHJKMNPQRSTVWXYZ]{12}")


def normalize_setup_code(setup_code: str) -> str:
    """Normalize a typed setup code the way the gridyard app does.

    Crockford Base32: case does not matter, O is read as 0, I and L as 1, spaces
    and hyphens are ignored.
    """
    code = re.sub(r"[\s-]", "", setup_code.upper())
    return code.replace("O", "0").replace("I", "1").replace("L", "1")


def device_title(device_id: str) -> str:
    """Return the name on the label and in mDNS, such as SM-ABCDEF."""
    return f"SM-{device_id[-6:].upper()}"


class GridyardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for gridyard.

    Steps: host, setup code, and for a device without profile the profile, the meter
    key of an encrypted meter, and the restart of the device with both.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host = ""
        self._setup_code = ""
        self._catalog = Catalog(catalog="", profiles=())
        self._profile_id: str | None = None
        self._meter_key: str | None = None
        self._send_task: asyncio.Task[None] | None = None
        self._send_error: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: GridyardConfigEntry,
    ) -> GridyardOptionsFlow:
        """Return the options flow."""
        return GridyardOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host of the device."""
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            return await self.async_step_setup_code()
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    async def async_step_setup_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the setup code and check it with a session."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._setup_code = normalize_setup_code(user_input[CONF_SETUP_CODE])
            if SETUP_CODE_PATTERN.fullmatch(self._setup_code) is None:
                # A wrong code would also lock the device for up to 300 s.
                errors[CONF_SETUP_CODE] = "invalid_setup_code"
            else:
                try:
                    info = await self._async_read_device()
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except ApiUnsupported:
                    errors["base"] = "api_unsupported"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(info.device_id)
                    self._abort_if_unique_id_configured()
                    if info.profile_id is not None:
                        return self._async_create_entry()
                    return await self.async_step_profile()
        return self.async_show_form(
            step_id="setup_code",
            data_schema=STEP_SETUP_CODE_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the meter profile of a device that has none."""
        errors = self._pop_send_error()
        if user_input is not None:
            profile_id = user_input[CONF_PROFILE]
            if not profile_in_catalog(self._catalog, profile_id):
                errors[CONF_PROFILE] = "invalid_profile"
            else:
                self._profile_id = profile_id
                if profile_encrypted(self._catalog, profile_id):
                    return await self.async_step_meter_key()
                return await self.async_step_send()
        return self.async_show_form(
            step_id="profile",
            data_schema=profile_schema(self._catalog, CONF_PROFILE),
            errors=errors,
        )

    async def async_step_meter_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the key of an encrypted meter."""
        errors = self._pop_send_error()
        if user_input is not None:
            meter_key = normalize_meter_key(user_input[CONF_METER_KEY])
            if not meter_key_valid(meter_key):
                errors[CONF_METER_KEY] = "invalid_meter_key"
            else:
                self._meter_key = meter_key
                return await self.async_step_send()
        return self.async_show_form(
            step_id="meter_key", data_schema=STEP_METER_KEY_DATA_SCHEMA, errors=errors
        )

    async def async_step_send(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Send profile and key; the device restarts, which takes up to a minute."""
        if self._send_task is None:
            # Not eager: the first call always shows the progress, as the flow expects.
            self._send_task = self.hass.async_create_task(
                self._async_send(), eager_start=False
            )
        if not self._send_task.done():
            return self.async_show_progress(
                step_id="send",
                progress_action="send_settings",
                progress_task=self._send_task,
            )
        task, self._send_task = self._send_task, None
        try:
            task.result()
        except GridyardError as err:
            self._send_error = settings_error(err)
        except Exception:
            _LOGGER.exception("Unexpected exception")
            self._send_error = "unknown"
        if self._send_error is None:
            return self.async_show_progress_done(next_step_id="finish")
        if self._send_error == "invalid_meter_key":
            return self.async_show_progress_done(next_step_id="meter_key")
        return self.async_show_progress_done(next_step_id="profile")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry after the device took the settings."""
        return self._async_create_entry()

    def _async_create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=device_title(str(self.unique_id)),
            data={CONF_HOST: self._host, CONF_SETUP_CODE: self._setup_code},
        )

    def _pop_send_error(self) -> dict[str, str]:
        """Return the error of the last sending as form errors, once."""
        error, self._send_error = self._send_error, None
        return {} if error is None else {"base": error}

    async def _async_read_device(self) -> DeviceInfo:
        """Read device-info, and the catalog if the device has no profile yet."""
        async with self._client() as client:
            info = await client.device_info()
            if info.profile_id is None:
                self._catalog = await client.profiles()
        return info

    async def _async_send(self) -> None:
        async with self._client() as client:
            await send_settings(client, self._profile_id, self._meter_key)

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[GridyardClient]:
        """Yield a client on a session that is released afterwards."""
        session = async_create_clientsession(
            self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar()
        )
        try:
            yield GridyardClient(session, self._host, self._setup_code)
        finally:
            session.detach()


class GridyardOptionsFlow(OptionsFlowWithReload):
    """Change profile and key on the device, and switch the update check.

    The entry reloads afterwards, so device model and sensors follow the profile.
    """

    def __init__(self) -> None:
        """Initialize the flow."""
        self._catalog: Catalog | None = None
        self._profile_id: str | None = None
        self._meter_key: str | None = None
        self._update_check = True
        self._send_task: asyncio.Task[None] | None = None
        self._send_error: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show profile, key and update check."""
        coordinator = self.config_entry.runtime_data
        if self._catalog is None:
            try:
                self._catalog = await coordinator.client.profiles()
            except GridyardError:
                return self.async_abort(reason="cannot_connect")
        current_profile = coordinator.device.profile_id
        error, self._send_error = self._send_error, None
        errors = {} if error is None else {"base": error}
        if user_input is not None:
            profile_id = user_input[CONF_PROFILE]
            meter_key = normalize_meter_key(user_input.get(CONF_METER_KEY, ""))
            if not profile_in_catalog(self._catalog, profile_id):
                errors[CONF_PROFILE] = "invalid_profile"
            elif meter_key and not meter_key_valid(meter_key):
                errors[CONF_METER_KEY] = "invalid_meter_key"
            else:
                self._profile_id = None if profile_id == current_profile else profile_id
                self._meter_key = meter_key or None
                self._update_check = user_input[CONF_UPDATE_CHECK]
                if self._profile_id is None and self._meter_key is None:
                    return self._async_save()
                return await self.async_step_send()
        schema = probatio.Schema(
            {
                probatio.Required(CONF_PROFILE): profile_selector(self._catalog),
                probatio.Optional(CONF_METER_KEY): METER_KEY_SELECTOR,
                probatio.Required(CONF_UPDATE_CHECK): BooleanSelector(),
            }
        )
        suggested = {
            CONF_PROFILE: current_profile,
            CONF_UPDATE_CHECK: self.config_entry.options.get(CONF_UPDATE_CHECK, True),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )

    async def async_step_send(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Send profile and key; the device restarts, which takes up to a minute."""
        if self._send_task is None:
            client = self.config_entry.runtime_data.client
            self._send_task = self.hass.async_create_task(
                send_settings(client, self._profile_id, self._meter_key),
                eager_start=False,
            )
        if not self._send_task.done():
            return self.async_show_progress(
                step_id="send",
                progress_action="send_settings",
                progress_task=self._send_task,
            )
        task, self._send_task = self._send_task, None
        try:
            task.result()
        except GridyardError as err:
            self._send_error = settings_error(err)
        except Exception:
            _LOGGER.exception("Unexpected exception")
            self._send_error = "unknown"
        if self._send_error is not None:
            return self.async_show_progress_done(next_step_id="init")
        return self.async_show_progress_done(next_step_id="save")

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the options after the device took the settings."""
        if self._profile_id is not None:
            self._remove_sensors()
        return self._async_save()

    def _async_save(self) -> ConfigFlowResult:
        return self.async_create_entry(data={CONF_UPDATE_CHECK: self._update_check})

    def _remove_sensors(self) -> None:
        """Remove the sensors of the old profile; the reload adds the new values."""
        registry = er.async_get(self.hass)
        for entry in er.async_entries_for_config_entry(
            registry, self.config_entry.entry_id
        ):
            if entry.domain == Platform.SENSOR:
                registry.async_remove(entry.entity_id)
