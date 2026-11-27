"""Test the gridyard config flow."""

from unittest.mock import AsyncMock

import pytest
from gridyard import (
    ApiUnsupported,
    CannotConnect,
    ConfigInvalid,
    GridyardError,
    InvalidAuth,
    ProfileUnknown,
)
from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntryState,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gridyard.const import (
    CONF_METER_KEY,
    CONF_PROFILE,
    CONF_SETUP_CODE,
    DOMAIN,
)

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


async def start_profile_step(hass: HomeAssistant) -> str:
    """Start the flow up to the profile step and return the flow id."""
    flow_id = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "profile"
    return flow_id


async def finish_progress(hass: HomeAssistant, flow_id: str) -> ConfigFlowResult:
    """Wait for the sending task and return the step after the progress."""
    await hass.async_block_till_done()
    return await hass.config_entries.flow.async_configure(flow_id)


async def test_profile_options_sorted_by_model(
    hass: HomeAssistant, device_without_profile: AsyncMock
) -> None:
    """Test the profile list is sorted by model and searchable."""
    flow_id = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_SETUP_CODE: SETUP_CODE}
    )

    selector = result["data_schema"].schema[CONF_PROFILE]
    assert selector.config["custom_value"] is True
    assert [option["value"] for option in selector.config["options"]] == [
        "iec-apator-12ec3",
        "sml-ebz-dd3",
        "dlms-iskra-am550",
    ]
    assert selector.config["options"][0]["label"] == "Apator 12EC3 (iec-apator-12ec3)"


async def test_profile_flow(
    hass: HomeAssistant, device_without_profile: AsyncMock
) -> None:
    """Test a device without profile gets one before the entry is created."""
    flow_id = await start_profile_step(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "sml-ebz-dd3"}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["progress_action"] == "send_settings"

    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_SETUP_CODE: SETUP_CODE}
    # The mock still reports no profile and no live record; setup copes with that.
    assert result["result"].state is ConfigEntryState.LOADED
    device_without_profile.set_profile.assert_awaited_once_with("sml-ebz-dd3")
    device_without_profile.set_meter_key.assert_not_called()


async def test_profile_flow_with_meter_key(
    hass: HomeAssistant, device_without_profile: AsyncMock
) -> None:
    """Test an encrypted meter asks for the key and sends it after the profile."""
    flow_id = await start_profile_step(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "dlms-iskra-am550"}
    )
    assert result["step_id"] == "meter_key"

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_METER_KEY: "0011 2233 4455 6677 8899 aabb ccdd eeff"}
    )
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    device_without_profile.set_profile.assert_awaited_once_with("dlms-iskra-am550")
    device_without_profile.set_meter_key.assert_awaited_once_with(
        "00112233445566778899AABBCCDDEEFF"
    )


@pytest.mark.usefixtures("device_without_profile")
async def test_profile_not_in_catalog(hass: HomeAssistant) -> None:
    """Test a typed value that is not a profile."""
    flow_id = await start_profile_step(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "no-such-profile"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROFILE: "invalid_profile"}


@pytest.mark.usefixtures("device_without_profile")
async def test_meter_key_format(hass: HomeAssistant) -> None:
    """Test a key with the wrong format is not sent."""
    flow_id = await start_profile_step(hass)
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "dlms-iskra-am550"}
    )

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_METER_KEY: "0011"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_METER_KEY: "invalid_meter_key"}


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (ProfileUnknown("profile: PROFILE_UNKNOWN"), "profile_unknown"),
        (GridyardError("device-info: expected state not reached"), "not_applied"),
        (CannotConnect("refused"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_profile_send_errors(
    hass: HomeAssistant,
    device_without_profile: AsyncMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test a failed profile change returns to the profile step and recovers."""
    flow_id = await start_profile_step(hass)
    device_without_profile.set_profile.side_effect = side_effect
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "sml-ebz-dd3"}
    )

    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "profile"
    assert result["errors"] == {"base": error}

    device_without_profile.set_profile.side_effect = None
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "sml-ebz-dd3"}
    )
    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_meter_key_rejected(
    hass: HomeAssistant, device_without_profile: AsyncMock
) -> None:
    """Test a key the device rejects returns to the key step."""
    flow_id = await start_profile_step(hass)
    device_without_profile.set_meter_key.side_effect = ConfigInvalid(
        "meter-key: CONFIG_INVALID"
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_PROFILE: "dlms-iskra-am550"}
    )
    await hass.config_entries.flow.async_configure(
        flow_id, {CONF_METER_KEY: "00112233445566778899AABBCCDDEEFF"}
    )

    result = await finish_progress(hass, flow_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "meter_key"
    assert result["errors"] == {"base": "invalid_meter_key"}
