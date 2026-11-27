"""Common fixtures for the gridyard tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from gridyard import Catalog, DeviceInfo, Profile, State
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)

from custom_components.gridyard.const import CONF_SETUP_CODE, DOMAIN

DEVICE_ID = "sm-0123456789ab"
HOST = "192.0.2.10"
SETUP_CODE = "AAAABBBBCCCC"
# Synthetic catalog with the profile of the state example.
CATALOG = Catalog(
    catalog="caf9acc67c01abf6",
    profiles=(
        Profile(id="iec-apator-12ec3", model="Apator 12EC3", rev=1, encrypted=False),
        Profile(id="sml-ebz-dd3", model="eBZ DD3", rev=1, encrypted=False),
    ),
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a gridyard config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="SM-6789AB",
        unique_id=DEVICE_ID,
        data={CONF_HOST: HOST, CONF_SETUP_CODE: SETUP_CODE},
    )


@pytest.fixture
def mock_gridyard_client() -> Generator[AsyncMock]:
    """Replace the gridyard client where the integration uses it."""
    with (
        patch(
            "custom_components.gridyard.config_flow.GridyardClient", autospec=True
        ) as client_class,
        patch("custom_components.gridyard.GridyardClient", new=client_class),
    ):
        client = client_class.return_value
        client.device_info.return_value = DeviceInfo.from_json(
            load_json_object_fixture("device-info.json")
        )
        client.state.return_value = State.from_json(
            load_json_object_fixture("state.json")
        )
        client.profiles.return_value = CATALOG
        yield client
