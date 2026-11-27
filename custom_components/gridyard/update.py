"""Firmware update of a gridyard device over the local API."""

from typing import Any

from gridyard import (
    API,
    DeviceError,
    FirmwareRelease,
    GridyardError,
    UpdateFailed,
    fetch_image,
)
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import GridyardConfigEntry, GridyardCoordinator
from .entity import GridyardEntity

# Coordinator-based platform; Home Assistant refuses a second install while one runs.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GridyardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the firmware update entity."""
    async_add_entities([GridyardUpdate(entry.runtime_data)])


class GridyardUpdate(GridyardEntity, UpdateEntity):
    """Firmware of the device, with the latest release from the manifest."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )
    _attr_translation_key = "firmware"

    def __init__(self, coordinator: GridyardCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device.device_id}_firmware"

    async def async_added_to_hass(self) -> None:
        """Also follow the firmware coordinator, if the update check is on."""
        await super().async_added_to_hass()
        firmware = self.coordinator.firmware
        if firmware is not None:
            self.async_on_remove(
                firmware.async_add_listener(self._handle_coordinator_update)
            )

    @property
    def _release(self) -> FirmwareRelease | None:
        """Return the latest release if the device can take it."""
        firmware = self.coordinator.firmware
        if firmware is None or not firmware.last_update_success:
            return None
        if firmware.data.min_api > API:
            return None
        return firmware.data

    @property
    def installed_version(self) -> str:
        """Return the firmware the device runs."""
        return self.coordinator.data.firmware

    @property
    def latest_version(self) -> str:
        """Return the latest release, or the installed version without an offer."""
        release = self._release
        return self.installed_version if release is None else release.version

    async def async_release_notes(self) -> str | None:
        """Return the notes of the latest release."""
        release = self._release
        return None if release is None else release.notes

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Download and check the image, then install it on the device."""
        release = self._release
        if release is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="no_release"
            )
        try:
            image = await fetch_image(async_get_clientsession(self.hass), release)
        except GridyardError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="download_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._set_progress(0)
        self.coordinator.updating = True
        try:
            await self.coordinator.client.update(
                release.version, image, self._on_progress
            )
        except UpdateFailed as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_fell_back",
                translation_placeholders={"error": str(err)},
            ) from err
        except DeviceError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_rejected",
                translation_placeholders={"error": str(err)},
            ) from err
        except GridyardError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            self.coordinator.updating = False
            self._set_progress(None)
            await self.coordinator.async_refresh()

    @callback
    def _on_progress(self, sent: int, total: int) -> None:
        """Show the upload progress in whole percent."""
        percentage = sent * 100 // total
        if percentage != self._attr_update_percentage:
            self._set_progress(percentage)

    @callback
    def _set_progress(self, percentage: int | None) -> None:
        """Show an install in progress (with percentage) or none (None)."""
        self._attr_in_progress = percentage is not None
        self._attr_update_percentage = percentage
        self.async_write_ha_state()
