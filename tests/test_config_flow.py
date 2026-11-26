"""Test the gridyard config flow."""

from unittest.mock import AsyncMock

import pytest
from gridyard import ApiUnsupported, CannotConnect, InvalidAuth
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gridyard.const import CONF_SETUP_CODE, DOMAIN

from .conftest import DEVICE_ID, HOST, SETUP_CODE


async def start_flow(hass: HomeAssistant) -> str:
    """Start the user flow, enter the host and return the flow id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "setup_code"
    assert result["errors"] == {}
    return result["flow_id"]


@pytest.mark.usefixtures("mock_gridyard_client")
@pytest.mark.parametrize(
    ("typed_code", "stored_code"),
    [
        (SETUP_CODE, SETUP_CODE),
        ("aaaa-bbbb cccc", SETUP_CODE),
        ("O1IL-oil0-2345", "011101102345"),
    ],
)
async def test_user_flow(
    hass: HomeAssistant, typed_code: str, stored_code: str
) -> None:
    """Test the flow creates an entry with the normalized setup code."""
    flow_id = await start_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: typed_code}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SM-6789AB"
    assert result["data"] == {CONF_HOST: HOST, CONF_SETUP_CODE: stored_code}
    assert result["result"].unique_id == DEVICE_ID


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CannotConnect("refused"), "cannot_connect"),
        (InvalidAuth("rejected"), "invalid_auth"),
        (ApiUnsupported("proto-ver: local API None, expected 1"), "api_unsupported"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_gridyard_client: AsyncMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors of the setup code step and recovery from them."""
    flow_id = await start_flow(hass)
    mock_gridyard_client.device_info.side_effect = side_effect

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_gridyard_client.device_info.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_setup_code(
    hass: HomeAssistant, mock_gridyard_client: AsyncMock
) -> None:
    """Test a code with the wrong format is not sent to the device."""
    flow_id = await start_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: "AAAABBBBCCCU"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SETUP_CODE: "invalid_setup_code"}
    mock_gridyard_client.device_info.assert_not_called()

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the flow aborts for a device that is already set up."""
    mock_config_entry.add_to_hass(hass)
    flow_id = await start_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
