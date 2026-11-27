"""Test the diagnostics download."""

import json

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from custom_components.gridyard.const import (
    CONF_METER_KEY,
    CONF_PROFILE,
    CONF_UPDATE_CHECK,
)

from . import setup_integration
from .conftest import DEVICE_ID, HOST, SETUP_CODE


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the download holds neither setup code, host nor the full device_id."""
    await setup_integration(hass, mock_config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    text = json.dumps(diagnostics)
    assert SETUP_CODE not in text
    assert HOST not in text
    assert DEVICE_ID not in text
    assert diagnostics["device"]["device_id"] == "…6789ab"
    assert diagnostics == snapshot


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_diagnostics_after_meter_key(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a meter key set in the options is not kept and not in the download."""
    key = "00112233445566778899AABBCCDDEEFF"
    await setup_integration(hass, mock_config_entry)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_PROFILE: "sml-ebz-dd3", CONF_METER_KEY: key, CONF_UPDATE_CHECK: True},
    )
    await hass.async_block_till_done()
    await hass.config_entries.options.async_configure(result["flow_id"])
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    assert key not in json.dumps(diagnostics)
    assert key.lower() not in json.dumps(diagnostics)
