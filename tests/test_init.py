"""Test setting up and unloading the gridyard integration."""

from unittest.mock import AsyncMock

import pytest
from gridyard import CannotConnect, InvalidAuth
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_load_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a config entry loads with the first state and unloads."""
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.data.device_id == "sm-0123456789ab"
    mock_gridyard_client.state.assert_awaited_once()

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("side_effect", "state"),
    [
        (CannotConnect("refused"), ConfigEntryState.SETUP_RETRY),
        (InvalidAuth("rejected"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
    side_effect: Exception,
    state: ConfigEntryState,
) -> None:
    """Test an unreachable device retries and a rejected code stops the entry."""
    mock_gridyard_client.state.side_effect = side_effect
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is state
