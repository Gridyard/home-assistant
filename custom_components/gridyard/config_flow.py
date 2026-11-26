"""Config flow for the gridyard integration."""

import logging
import re
from typing import Any

import aiohttp
import probatio
from gridyard import (
    ApiUnsupported,
    CannotConnect,
    DeviceInfo,
    GridyardClient,
    InvalidAuth,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_SETUP_CODE, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): str})
STEP_SETUP_CODE_DATA_SCHEMA = probatio.Schema({probatio.Required(CONF_SETUP_CODE): str})
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
    """Handle a config flow for gridyard."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host = ""

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
            setup_code = normalize_setup_code(user_input[CONF_SETUP_CODE])
            if SETUP_CODE_PATTERN.fullmatch(setup_code) is None:
                # A wrong code would also lock the device for up to 300 s.
                errors[CONF_SETUP_CODE] = "invalid_setup_code"
            else:
                try:
                    info = await self._async_device_info(setup_code)
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
                    return self.async_create_entry(
                        title=device_title(info.device_id),
                        data={CONF_HOST: self._host, CONF_SETUP_CODE: setup_code},
                    )
        return self.async_show_form(
            step_id="setup_code",
            data_schema=STEP_SETUP_CODE_DATA_SCHEMA,
            errors=errors,
        )

    async def _async_device_info(self, setup_code: str) -> DeviceInfo:
        """Open a session with the device and read device-info."""
        session = async_create_clientsession(
            self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar()
        )
        try:
            client = GridyardClient(session, self._host, setup_code)
            return await client.device_info()
        finally:
            session.detach()
