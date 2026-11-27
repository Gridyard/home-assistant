"""Sensors for the values of a gridyard device."""

from decimal import Decimal

from gridyard import Quality, Value
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import GridyardConfigEntry, GridyardCoordinator
from .entity import GridyardEntity

# Coordinator-based platform; the coordinator serializes requests to the device.
PARALLEL_UPDATES = 0

# Values from records of these qualities are shown; others make the sensors unavailable.
USABLE_QUALITIES = {Quality.VALID, Quality.PARTIAL}
PHASES = {1: "L1", 2: "L2", 3: "L3", 4: "N"}

_TOTAL = SensorStateClass.TOTAL_INCREASING
_MEASUREMENT = SensorStateClass.MEASUREMENT


def _energy(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=_TOTAL,
    )


def _power(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=_MEASUREMENT,
    )


def _reactive_energy(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.REACTIVE_ENERGY,
        native_unit_of_measurement=UnitOfReactiveEnergy.VOLT_AMPERE_REACTIVE_HOUR,
        state_class=_TOTAL,
    )


def _temperature(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=_MEASUREMENT,
    )


# One description per quantity `q`, as in the contract (Home Assistant mapping).
SENSORS: dict[str, SensorEntityDescription] = {
    description.key: description
    for description in (
        _energy("energy_import"),
        _energy("energy_export"),
        _power("power"),
        _power("power_import"),
        _power("power_export"),
        _reactive_energy("reactive_energy_import"),
        _reactive_energy("reactive_energy_export"),
        SensorEntityDescription(
            key="reactive_power",
            device_class=SensorDeviceClass.REACTIVE_POWER,
            native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="apparent_power",
            device_class=SensorDeviceClass.APPARENT_POWER,
            native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="current",
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="frequency",
            device_class=SensorDeviceClass.FREQUENCY,
            native_unit_of_measurement=UnitOfFrequency.HERTZ,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="power_factor",
            device_class=SensorDeviceClass.POWER_FACTOR,
            state_class=_MEASUREMENT,
        ),
        SensorEntityDescription(
            key="phase_angle",
            native_unit_of_measurement=DEGREE,
            state_class=SensorStateClass.MEASUREMENT_ANGLE,
        ),
        _energy("heat_energy"),
        SensorEntityDescription(
            key="volume",
            device_class=SensorDeviceClass.VOLUME,
            native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
            state_class=_TOTAL,
        ),
        SensorEntityDescription(
            key="flow",
            device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
            native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
            state_class=_MEASUREMENT,
        ),
        _temperature("flow_temperature"),
        _temperature("return_temperature"),
        SensorEntityDescription(
            key="operating_time",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            state_class=_TOTAL,
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GridyardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for every value of the record, also values that appear later.

    Right after setup the device may have no record yet, and a new profile brings
    other values, so every update checks for values without a sensor.
    """
    coordinator = entry.runtime_data
    known: set[tuple[str, int, int]] = set()

    @callback
    def add_new_sensors() -> None:
        record = coordinator.data.record
        if record is None:
            return
        new_values = [
            value
            for value in record.values
            if value.quantity in SENSORS and _key(value) not in known
        ]
        known.update(_key(value) for value in new_values)
        async_add_entities(GridyardSensor(coordinator, value) for value in new_values)

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


def _key(value: Value) -> tuple[str, int, int]:
    return (value.quantity, value.tariff, value.phase)


def _translation_key(quantity: str, tariff: int, phase: int) -> str:
    """Return the name key: the quantity, with a tariff and phase suffix if set."""
    suffix = ("_tariff" if tariff else "") + ("_phase" if phase else "")
    return quantity + suffix


class GridyardSensor(GridyardEntity, SensorEntity):
    """One value of the meter: quantity, tariff and phase."""

    def __init__(self, coordinator: GridyardCoordinator, value: Value) -> None:
        """Initialize the sensor for the quantity, tariff and phase of value."""
        super().__init__(coordinator)
        self.entity_description = SENSORS[value.quantity]
        self._value_key = _key(value)
        quantity, tariff, phase = self._value_key
        device_id = coordinator.device.device_id
        self._attr_unique_id = f"{device_id}_{quantity}_{tariff}_{phase}"
        self._attr_translation_key = _translation_key(quantity, tariff, phase)
        self._attr_translation_placeholders = {
            "tariff": str(tariff),
            "phase": PHASES.get(phase, str(phase)),
        }

    @property
    def _value(self) -> Value | None:
        """Return the value of this sensor if the record is usable."""
        record = self.coordinator.data.record
        if record is None or record.quality not in USABLE_QUALITIES:
            return None
        for value in record.values:
            if _key(value) == self._value_key:
                return value
        return None

    @property
    def available(self) -> bool:
        """Return if the latest record has a usable value for this sensor."""
        return super().available and self._value is not None

    @property
    def native_value(self) -> Decimal | None:
        """Return the value."""
        value = self._value
        return None if value is None else value.value
