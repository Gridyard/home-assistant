"""Constants for the gridyard integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gridyard"
CONF_SETUP_CODE: Final = "setup_code"
# Fixed polling interval of state; Home Assistant does not allow a configurable one.
UPDATE_INTERVAL: Final = timedelta(seconds=5)
CONF_PROFILE: Final = "profile"
CONF_METER_KEY: Final = "meter_key"
CONF_UPDATE_CHECK: Final = "update_check"
# manifest.json of the latest firmware release, read at most every 6 h (assumption).
FIRMWARE_CHECK_INTERVAL: Final = timedelta(hours=6)
# Development only: a test instance reads the manifest from this address instead.
MANIFEST_URL_ENV: Final = "GRIDYARD_MANIFEST_URL"
