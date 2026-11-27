"""Base entity for gridyard."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GridyardCoordinator


class GridyardEntity(CoordinatorEntity[GridyardCoordinator]):
    """Entity of a gridyard device; the model is the meter of the active profile."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GridyardCoordinator) -> None:
        """Initialize the entity and its device."""
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            manufacturer="gridyard",
            model=coordinator.model,
            model_id=device.profile_id,
            name=coordinator.config_entry.title,
            sw_version=device.firmware,
        )
