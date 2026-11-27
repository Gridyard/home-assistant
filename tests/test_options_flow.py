"""Test the gridyard options flow."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from gridyard import CannotConnect, ProfileUnknown, Value
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gridyard.const import (
    CONF_METER_KEY,
    CONF_PROFILE,
    CONF_UPDATE_CHECK,
)

from . import setup_integration

ENERGY_IMPORT = "sensor.sm_6789ab_energy_import"
CURRENT_L1 = "sensor.sm_6789ab_current_l1"


async def start_options(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Open the options with the current profile preset and return the flow id."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description
    }
    assert suggested == {CONF_PROFILE: "sml-ebz-dd3", CONF_UPDATE_CHECK: True}
    return result["flow_id"]


async def finish_progress(hass: HomeAssistant, flow_id: str) -> dict:
    """Wait for the sending task and return the step after the progress."""
    await hass.async_block_till_done()
    return await hass.config_entries.options.async_configure(flow_id)


async def test_update_check_only(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test switching the update check sends nothing to the device."""
    await setup_integration(hass, mock_config_entry)
    flow_id = await start_options(hass, mock_config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id, {CONF_PROFILE: "sml-ebz-dd3", CONF_UPDATE_CHECK: False}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_UPDATE_CHECK: False}
    mock_gridyard_client.set_profile.assert_not_called()
    mock_gridyard_client.set_meter_key.assert_not_called()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_change_profile(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a new profile is sent and only sensors of the new values remain."""
    state = mock_gridyard_client.state.return_value
    current = Value(quantity="current", tariff=0, phase=1, value=Decimal("1.5"))
    record = replace(state.record, values=(*state.record.values, current))
    mock_gridyard_client.state.return_value = replace(state, record=record)
    await setup_integration(hass, mock_config_entry)
    assert entity_registry.async_get(CURRENT_L1) is not None
    entity_registry.async_update_entity(ENERGY_IMPORT, name="Renamed")
    flow_id = await start_options(hass, mock_config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id, {CONF_PROFILE: "iec-apator-12ec3", CONF_UPDATE_CHECK: True}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    mock_gridyard_client.state.return_value = state
    result = await finish_progress(hass, flow_id)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_gridyard_client.set_profile.assert_awaited_once_with("iec-apator-12ec3")
    mock_gridyard_client.set_meter_key.assert_not_called()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert entity_registry.async_get(CURRENT_L1) is None
    # Home Assistant restores the settings of a sensor that comes back.
    assert entity_registry.async_get(ENERGY_IMPORT).name == "Renamed"


async def test_profile_for_device_without_profile(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_without_profile: AsyncMock,
) -> None:
    """Test the options give a profile to a device that has none."""
    await setup_integration(hass, mock_config_entry)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE: "sml-ebz-dd3", CONF_UPDATE_CHECK: True}
    )
    result = await finish_progress(hass, result["flow_id"])
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    device_without_profile.set_profile.assert_awaited_once_with("sml-ebz-dd3")
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_meter_key(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a new key is sent without changing the profile."""
    await setup_integration(hass, mock_config_entry)
    flow_id = await start_options(hass, mock_config_entry)

    await hass.config_entries.options.async_configure(
        flow_id,
        {
            CONF_PROFILE: "sml-ebz-dd3",
            CONF_METER_KEY: "00112233445566778899aabbccddeeff",
            CONF_UPDATE_CHECK: True,
        },
    )
    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    mock_gridyard_client.set_profile.assert_not_called()
    mock_gridyard_client.set_meter_key.assert_awaited_once_with(
        "00112233445566778899AABBCCDDEEFF"
    )


@pytest.mark.parametrize(
    ("user_input", "error"),
    [
        ({CONF_PROFILE: "no-such-profile"}, {CONF_PROFILE: "invalid_profile"}),
        (
            {CONF_PROFILE: "sml-ebz-dd3", CONF_METER_KEY: "0011"},
            {CONF_METER_KEY: "invalid_meter_key"},
        ),
    ],
)
async def test_invalid_input(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
    user_input: dict[str, str],
    error: dict[str, str],
) -> None:
    """Test input that is not sent to the device."""
    await setup_integration(hass, mock_config_entry)
    flow_id = await start_options(hass, mock_config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id, {**user_input, CONF_UPDATE_CHECK: True}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error
    mock_gridyard_client.set_profile.assert_not_called()


async def test_send_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a failed profile change shows the form again with the error."""
    await setup_integration(hass, mock_config_entry)
    mock_gridyard_client.set_profile.side_effect = ProfileUnknown("PROFILE_UNKNOWN")
    flow_id = await start_options(hass, mock_config_entry)

    await hass.config_entries.options.async_configure(
        flow_id, {CONF_PROFILE: "iec-apator-12ec3", CONF_UPDATE_CHECK: True}
    )
    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "profile_unknown"}


async def test_catalog_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test the options abort when the catalog cannot be read."""
    await setup_integration(hass, mock_config_entry)
    mock_gridyard_client.profiles.side_effect = CannotConnect("refused")

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"
