"""Test the firmware update entity."""

from collections.abc import Callable
from dataclasses import replace
from unittest.mock import ANY, AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from gridyard import (
    CannotConnect,
    GridyardError,
    UpdateFailed,
    UpdateFellBack,
    UpdateRejected,
)
from homeassistant.components.update import (
    ATTR_IN_PROGRESS,
    ATTR_INSTALLED_VERSION,
    ATTR_LATEST_VERSION,
    SERVICE_INSTALL,
)
from homeassistant.components.update import (
    DOMAIN as UPDATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.gridyard.const import CONF_UPDATE_CHECK, DOMAIN, UPDATE_INTERVAL

from . import setup_integration
from .conftest import DEVICE_ID, IMAGE, RELEASE

FIRMWARE = "update.sm_6789ab_firmware"


async def install(hass: HomeAssistant) -> None:
    """Call the install action of the firmware entity."""
    await hass.services.async_call(
        UPDATE_DOMAIN, SERVICE_INSTALL, {ATTR_ENTITY_ID: FIRMWARE}, blocking=True
    )


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_offer(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the latest release is offered with its notes."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_INSTALLED_VERSION] == "v0.5.0"
    assert state.attributes[ATTR_LATEST_VERSION] == "v0.6.0"

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "update/release_notes", "entity_id": FIRMWARE}
    )
    result = await client.receive_json()
    assert result["result"] == "Synthetic release notes"


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_update_check_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fetch_release: AsyncMock,
) -> None:
    """Test no request goes to GitHub while the update check is off."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_UPDATE_CHECK: False}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_LATEST_VERSION] == "v0.5.0"
    mock_fetch_release.assert_not_called()


@pytest.mark.usefixtures("mock_gridyard_client")
@pytest.mark.parametrize(
    "release",
    [replace(RELEASE, min_api=2), GridyardError("manifest: unexpected response")],
    ids=["newer-api", "broken-manifest"],
)
async def test_no_offer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fetch_release: AsyncMock,
    release: object,
) -> None:
    """Test a release the device cannot take or a broken manifest offers nothing."""
    if isinstance(release, Exception):
        mock_fetch_release.side_effect = release
    else:
        mock_fetch_release.return_value = release

    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_LATEST_VERSION] == "v0.5.0"


@pytest.mark.usefixtures("mock_fetch_image")
async def test_install(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test the image goes to the device with progress, then the new version shows."""
    await setup_integration(hass, mock_config_entry)
    progress_states: list[tuple[bool, object]] = []

    async def update(
        version: str, image: bytes, on_progress: Callable[[int, int], None]
    ) -> None:
        for sent in (0, len(image) // 2, len(image)):
            on_progress(sent, len(image))
            state = hass.states.get(FIRMWARE)
            progress_states.append(
                (
                    state.attributes[ATTR_IN_PROGRESS],
                    state.attributes["update_percentage"],
                )
            )
        new_state = mock_gridyard_client.state.return_value
        mock_gridyard_client.state.return_value = replace(new_state, firmware=version)

    mock_gridyard_client.update.side_effect = update

    await install(hass)

    mock_gridyard_client.update.assert_awaited_once_with("v0.6.0", IMAGE, ANY)
    # After the last block the device restarts; that shows without a percentage.
    assert progress_states == [(True, 0), (True, 50), (True, None)]
    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_OFF
    assert state.attributes[ATTR_IN_PROGRESS] is False
    assert state.attributes[ATTR_INSTALLED_VERSION] == "v0.6.0"
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), mock_config_entry.entry_id
    )
    assert device.sw_version == "v0.6.0"


@pytest.mark.usefixtures("mock_fetch_image")
@pytest.mark.parametrize(
    ("error", "translation_key"),
    [
        (UpdateFellBack("update: device fell back", "v0.5.0"), "update_fell_back"),
        (UpdateFailed("update-begin: UPDATE_FAILED"), "update_failed"),
        (UpdateRejected("update-begin: UPDATE_REJECTED"), "update_rejected"),
        (CannotConnect("update: ServerDisconnectedError"), "update_failed"),
    ],
)
async def test_install_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
    error: Exception,
    translation_key: str,
) -> None:
    """Test a failed update says why and leaves no progress behind."""
    await setup_integration(hass, mock_config_entry)
    mock_gridyard_client.update.side_effect = error

    with pytest.raises(HomeAssistantError) as raised:
        await install(hass)

    assert raised.value.translation_key == translation_key
    state = hass.states.get(FIRMWARE)
    assert state.attributes[ATTR_IN_PROGRESS] is False
    assert state.attributes[ATTR_INSTALLED_VERSION] == "v0.5.0"
    assert state.state == STATE_ON


async def test_install_download_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
    mock_fetch_image: AsyncMock,
) -> None:
    """Test an image that does not match its release never reaches the device."""
    await setup_integration(hass, mock_config_entry)
    mock_fetch_image.side_effect = GridyardError("image: SHA-256 mismatch")

    with pytest.raises(HomeAssistantError) as raised:
        await install(hass)

    assert raised.value.translation_key == "download_failed"
    mock_gridyard_client.update.assert_not_called()


async def test_polling_pauses_during_upload(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test the coordinator keeps the last state while an upload runs."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    calls = mock_gridyard_client.state.await_count

    coordinator.updating = True
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_gridyard_client.state.await_count == calls
    assert coordinator.last_update_success
