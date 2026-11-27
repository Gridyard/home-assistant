"""Test discovery by mDNS and reauthentication."""

from dataclasses import replace
from ipaddress import ip_address
from unittest.mock import AsyncMock

import pytest
from gridyard import InvalidAuth
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_ZEROCONF,
    ConfigEntryState,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gridyard.const import CONF_SETUP_CODE, DOMAIN

from . import setup_integration
from .conftest import DEVICE_ID, HOST, SETUP_CODE

NEW_HOST = "192.0.2.20"


def discovery(api: str = "1", device_id: str | None = DEVICE_ID) -> ZeroconfServiceInfo:
    """Return the mDNS announcement of the test device (synthetic)."""
    properties = {"fw": "v0.5.0", "api": api, "mode": "local"}
    if device_id is not None:
        properties["id"] = device_id
    return ZeroconfServiceInfo(
        ip_address=ip_address(NEW_HOST),
        ip_addresses=[ip_address(NEW_HOST)],
        port=80,
        hostname="sm-6789ab.local.",
        type="_gridyard._tcp.local.",
        name="SM-6789AB._gridyard._tcp.local.",
        properties=properties,
    )


async def start_discovery(hass: HomeAssistant, api: str = "1") -> dict:
    """Start the flow from an mDNS announcement."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery(api)
    )


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_discovered_device(hass: HomeAssistant) -> None:
    """Test a found device is set up with its address and the setup code."""
    result = await start_discovery(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"name": "SM-6789AB"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "setup_code"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: NEW_HOST, CONF_SETUP_CODE: SETUP_CODE}
    assert result["result"].unique_id == DEVICE_ID


async def test_known_device_new_address(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a known device that got a new address updates its entry."""
    mock_config_entry.add_to_hass(hass)

    result = await start_discovery(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == NEW_HOST


async def test_ignored_device(hass: HomeAssistant) -> None:
    """Test a device the user ignored is not offered again."""
    MockConfigEntry(
        domain=DOMAIN, unique_id=DEVICE_ID, source=SOURCE_IGNORE
    ).add_to_hass(hass)

    result = await start_discovery(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_other_api(hass: HomeAssistant) -> None:
    """Test a device with another local API is not set up."""
    result = await start_discovery(hass, api="2")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "api_unsupported"


async def test_announcement_without_id(hass: HomeAssistant) -> None:
    """Test another device announcing _gridyard._tcp without an ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery(device_id=None)
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery_info"


async def test_rejected_code_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a rejected setup code stops the entry and asks for the code again."""
    mock_gridyard_client.state.side_effect = InvalidAuth("rejected")

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a new setup code is checked, stored and the entry reloads."""
    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_gridyard_client.device_info.side_effect = InvalidAuth("rejected")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: "BBBBCCCCDDDD"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: "BBBB-CCCC-DDDU"}
    )
    assert result["errors"] == {CONF_SETUP_CODE: "invalid_setup_code"}

    mock_gridyard_client.device_info.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: "bbbb-cccc-dddd"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    mock_gridyard_client.profiles.assert_not_called()
    assert mock_config_entry.data == {CONF_HOST: HOST, CONF_SETUP_CODE: "BBBBCCCCDDDD"}


async def test_reauth_other_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test a code that opens another device at that address is refused."""
    await setup_integration(hass, mock_config_entry)
    info = mock_gridyard_client.device_info.return_value
    mock_gridyard_client.device_info.return_value = replace(
        info, device_id="sm-ffffffffffff"
    )
    result = await mock_config_entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reauth_reads_no_catalog(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    device_without_profile: AsyncMock,
) -> None:
    """Test reauth of a device without profile only checks the code."""
    await setup_integration(hass, mock_config_entry)
    result = await mock_config_entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SETUP_CODE: SETUP_CODE}
    )

    assert result["reason"] == "reauth_successful"
    device_without_profile.profiles.assert_not_called()
