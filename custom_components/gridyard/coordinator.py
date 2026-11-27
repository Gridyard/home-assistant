"""Coordinators: device state every 5 s, firmware releases every 6 h."""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

from gridyard import (
    MANIFEST_URL,
    DeviceInfo,
    FirmwareRelease,
    GridyardClient,
    GridyardError,
    InvalidAuth,
    State,
    fetch_release,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, FIRMWARE_CHECK_INTERVAL, MANIFEST_URL_ENV, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type GridyardConfigEntry = ConfigEntry[GridyardCoordinator]


class GridyardFirmwareCoordinator(DataUpdateCoordinator[FirmwareRelease]):
    """Read manifest.json of the latest firmware release every 6 h.

    Exists only while the update check is on, so no request goes to GitHub
    otherwise.
    """

    config_entry: GridyardConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: GridyardConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} firmware",
            update_interval=FIRMWARE_CHECK_INTERVAL,
        )
        self._url = os.environ.get(MANIFEST_URL_ENV, MANIFEST_URL)

    async def _async_update_data(self) -> FirmwareRelease:
        """Read the release; a broken manifest means no offer and a log entry."""
        try:
            return await fetch_release(async_get_clientsession(self.hass), self._url)
        except GridyardError as err:
            msg = f"Firmware manifest: {err}"
            raise UpdateFailed(msg) from err


class GridyardCoordinator(DataUpdateCoordinator[State]):
    """Read the latest record and device state every UPDATE_INTERVAL."""

    config_entry: GridyardConfigEntry
    device: DeviceInfo
    firmware: GridyardFirmwareCoordinator | None = None
    # Set during a firmware upload; polling pauses and keeps the last state.
    updating = False

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GridyardConfigEntry,
        client: GridyardClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_setup(self) -> None:
        """Read device-info once, for the device registry."""
        with _map_errors():
            self.device = await self.client.device_info()

    async def _async_update_data(self) -> State:
        """Read state from the device, except while a firmware upload runs."""
        if self.updating:
            return self.data
        with _map_errors():
            state = await self.client.state()
        if state.firmware != self.device.firmware:
            self._set_firmware(state.firmware)
        return state

    def _set_firmware(self, firmware: str) -> None:
        """Show a new firmware in the device registry, after any kind of update."""
        self.device = replace(self.device, firmware=firmware)
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, self.device.device_id), self.config_entry.entry_id
        )
        if device is not None:
            registry.async_update_device(device.id, sw_version=firmware)


@contextmanager
def _map_errors() -> Iterator[None]:
    """Turn library errors into the errors the coordinator expects."""
    try:
        yield
    except InvalidAuth as err:
        # Reauthentication follows with discovery; until then the entry stops.
        msg = "The device rejected the setup code"
        raise ConfigEntryError(msg) from err
    except GridyardError as err:
        raise UpdateFailed(str(err)) from err
