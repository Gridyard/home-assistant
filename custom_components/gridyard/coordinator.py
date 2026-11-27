"""Coordinator that polls the state of a gridyard device."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from gridyard import DeviceInfo, GridyardClient, GridyardError, InvalidAuth, State
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type GridyardConfigEntry = ConfigEntry[GridyardCoordinator]


class GridyardCoordinator(DataUpdateCoordinator[State]):
    """Read the latest record and device state every UPDATE_INTERVAL."""

    config_entry: GridyardConfigEntry
    device: DeviceInfo

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
        """Read state from the device."""
        with _map_errors():
            return await self.client.state()


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
