"""Constants for the gridyard integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gridyard"
CONF_SETUP_CODE: Final = "setup_code"
# Fixed polling interval of state; Home Assistant does not allow a configurable one.
UPDATE_INTERVAL: Final = timedelta(seconds=5)
