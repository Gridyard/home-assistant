"""Meter profile and meter key: form fields, input checks and sending to the device."""

import re

import probatio
from gridyard import (
    CannotConnect,
    Catalog,
    ConfigInvalid,
    GridyardClient,
    GridyardError,
    ProfileUnknown,
    SessionLost,
)
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

# DLMS key: 32 hex characters, as the gridyard app checks it.
METER_KEY_PATTERN = re.compile(r"[0-9A-F]{32}")
METER_KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def profile_selector(catalog: Catalog) -> SelectSelector:
    """Return a searchable list of the profiles, sorted by meter model.

    The frontend searches the list only with custom_value; a typed value that is not
    a profile is rejected by profile_in_catalog().
    """
    profiles = sorted(
        catalog.profiles, key=lambda profile: (profile.model.casefold(), profile.id)
    )
    options = [
        SelectOptionDict(value=profile.id, label=f"{profile.model} ({profile.id})")
        for profile in profiles
    ]
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            mode=SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=False,
        )
    )


def profile_schema(catalog: Catalog, field: str) -> probatio.Schema:
    """Return the form with the profile list."""
    return probatio.Schema({probatio.Required(field): profile_selector(catalog)})


def profile_in_catalog(catalog: Catalog, profile_id: str) -> bool:
    """Return if the profile is in the catalog of the device."""
    return any(profile.id == profile_id for profile in catalog.profiles)


def profile_encrypted(catalog: Catalog, profile_id: str) -> bool:
    """Return if the meter of the profile needs a key."""
    return any(
        profile.id == profile_id and profile.encrypted for profile in catalog.profiles
    )


def normalize_meter_key(meter_key: str) -> str:
    """Normalize a typed key like the gridyard app: no spaces, upper case."""
    return re.sub(r"\s", "", meter_key).upper()


def meter_key_valid(meter_key: str) -> bool:
    """Return if the normalized key has the format of a DLMS key."""
    return METER_KEY_PATTERN.fullmatch(meter_key) is not None


async def send_settings(
    client: GridyardClient, profile_id: str | None, meter_key: str | None
) -> None:
    """Send the profile, then the key, like the app; each waits for the restart."""
    if profile_id is not None:
        await client.set_profile(profile_id)
    if meter_key is not None:
        await client.set_meter_key(meter_key)


def settings_error(err: GridyardError) -> str:
    """Return the error key for an error from send_settings."""
    if isinstance(err, ProfileUnknown):
        return "profile_unknown"
    if isinstance(err, ConfigInvalid):
        return "invalid_meter_key"
    if isinstance(err, CannotConnect | SessionLost):
        return "cannot_connect"
    # set_profile gave up waiting for the device to report the profile.
    return "not_applied"
