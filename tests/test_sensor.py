"""Test the gridyard sensors."""

from collections.abc import Generator
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from gridyard import CannotConnect, Quality, State
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_json_object_fixture,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.gridyard.const import DOMAIN, UPDATE_INTERVAL

from . import setup_integration
from .conftest import DEVICE_ID

ENERGY_IMPORT = "sensor.sm_6789ab_energy_import"
POWER_L1 = "sensor.sm_6789ab_power_l1"


@pytest.fixture(autouse=True)
def only_sensors() -> Generator[None]:
    """Load only the sensor platform."""
    with patch("custom_components.gridyard.PLATFORMS", [Platform.SENSOR]):
        yield


async def next_update(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Move time to the next poll of the coordinator."""
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def with_quality(state: State, quality: Quality) -> State:
    """Return state with another record quality."""
    return replace(state, record=replace(state.record, quality=quality))


@pytest.mark.usefixtures("mock_gridyard_client")
async def test_sensors(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test one sensor per quantity, tariff and phase of the state example."""
    await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


async def test_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test the device shows the meter model of the active profile."""
    await setup_integration(hass, mock_config_entry)

    mock_gridyard_client.profiles.assert_not_called()

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "gridyard"
    assert device.model == "eBZ DD3"
    assert device.model_id == "sml-ebz-dd3"
    assert device.sw_version == "v0.5.0"
    assert device.name == "SM-6789AB"


async def test_device_without_profile(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    device_without_profile: AsyncMock,
) -> None:
    """Test a device without profile and live record loads without sensors."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    device_without_profile.profiles.assert_not_called()


@pytest.mark.parametrize(
    "quality", [Quality.STALE, Quality.UNAVAILABLE, Quality.INVALID, Quality.UNKNOWN]
)
async def test_unusable_quality(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
    quality: Quality,
) -> None:
    """Test sensors are unavailable when the record must not be used."""
    await setup_integration(hass, mock_config_entry)
    state = mock_gridyard_client.state.return_value
    mock_gridyard_client.state.return_value = with_quality(state, quality)

    await next_update(hass, freezer)

    assert hass.states.get(ENERGY_IMPORT).state == STATE_UNAVAILABLE
    assert hass.states.get(POWER_L1).state == STATE_UNAVAILABLE


async def test_update_error(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test sensors are unavailable while the device does not answer."""
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(ENERGY_IMPORT).state == "12345.6789"

    mock_gridyard_client.state.side_effect = CannotConnect("refused")
    await next_update(hass, freezer)

    assert hass.states.get(ENERGY_IMPORT).state == STATE_UNAVAILABLE

    mock_gridyard_client.state.side_effect = None
    await next_update(hass, freezer)

    assert hass.states.get(ENERGY_IMPORT).state == "12345.6789"
    assert mock_gridyard_client.state.await_count == 3


async def test_sensors_added_later(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_gridyard_client: AsyncMock,
) -> None:
    """Test sensors appear once the device has its first record."""
    state = mock_gridyard_client.state.return_value
    mock_gridyard_client.state.return_value = State.from_json(
        load_json_object_fixture("state-without-record.json")
    )
    await setup_integration(hass, mock_config_entry)

    assert not er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )

    mock_gridyard_client.state.return_value = state
    await next_update(hass, freezer)

    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert len(entries) == 11
    assert hass.states.get(ENERGY_IMPORT).state == "12345.6789"
