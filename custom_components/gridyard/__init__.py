"""The gridyard integration."""

import aiohttp
from gridyard import GridyardClient
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_SETUP_CODE, CONF_UPDATE_CHECK
from .coordinator import (
    GridyardConfigEntry,
    GridyardCoordinator,
    GridyardFirmwareCoordinator,
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.UPDATE]


def create_client(hass: HomeAssistant, host: str, setup_code: str) -> GridyardClient:
    """Return a client with its own HTTP session.

    The library sets the session cookie of the device itself; the cookie jar of a
    shared session would replace it for host names.
    """
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    return GridyardClient(session, host, setup_code)


async def async_setup_entry(hass: HomeAssistant, entry: GridyardConfigEntry) -> bool:
    """Set up gridyard from a config entry."""
    client = create_client(hass, entry.data[CONF_HOST], entry.data[CONF_SETUP_CODE])
    coordinator = GridyardCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    if entry.options.get(CONF_UPDATE_CHECK, True):
        coordinator.firmware = GridyardFirmwareCoordinator(hass, entry)
        # Not first_refresh: GitHub being down must not stop the setup.
        await coordinator.firmware.async_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GridyardConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
