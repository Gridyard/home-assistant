"""Common fixtures for the gridyard tests."""

import pytest
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.gridyard.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a gridyard config entry."""
    return MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "192.0.2.10"})
