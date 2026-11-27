"""Diagnostics download of a gridyard entry."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_METER_KEY, CONF_SETUP_CODE
from .coordinator import GridyardConfigEntry

# The meter key is never stored in Home Assistant; redacted in case that changes.
TO_REDACT = {CONF_HOST, CONF_METER_KEY, CONF_SETUP_CODE}


def _short(device_id: str) -> str:
    """Keep only the last 6 characters of the device_id."""
    return f"…{device_id[-6:]}"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GridyardConfigEntry
) -> dict[str, Any]:
    """Return entry, device and state; no code, key, readings or full device_id."""
    coordinator = entry.runtime_data
    state = coordinator.data
    record = state.record
    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "device": {**asdict(coordinator.device), "device_id": _short(state.device_id)},
        "state": {
            "device_id": _short(state.device_id),
            "firmware": state.firmware,
            "mode": state.mode,
            "uptime_ms": state.uptime_ms,
            "axes": {name: asdict(axis) for name, axis in state.axes.items()},
            "diag": state.diag,
        },
        "record": None
        if record is None
        else {
            "quality": record.quality.value,
            "age_ms": record.age_ms,
            "profile_id": record.profile_id,
            # Which values the meter sends, not the readings: downloads end up in
            # public issues, and readings are personal data.
            "values": [
                {"q": value.quantity, "t": value.tariff, "p": value.phase}
                for value in record.values
            ],
        },
        "firmware_release": None
        if coordinator.firmware is None or not coordinator.firmware.last_update_success
        else asdict(coordinator.firmware.data),
    }
