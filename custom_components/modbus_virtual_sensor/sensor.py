"""Sensor entities exposing what the virtual sensor reports to the master."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import ModbusVirtualSensorBridge
from .const import DOMAIN
from .entity import BridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: ModbusVirtualSensorBridge = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ReportedTemperature(bridge),
            ReportedHumidity(bridge),
            PollCount(bridge),
            LastPoll(bridge),
        ]
    )


class ReportedTemperature(BridgeEntity, SensorEntity):
    """The aggregated temperature served to the master."""

    _attr_translation_key = "reported_temperature"
    _attr_name = "Reported temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "reported_temperature")

    @property
    def native_value(self) -> float | None:
        return self._bridge.reported_temp

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "aggregation": self._bridge.temp_agg,
            "sources_total": len(self._bridge.temp_entities),
            "sources_available": self._bridge.temp_available,
        }


class ReportedHumidity(BridgeEntity, SensorEntity):
    """The aggregated humidity served to the master."""

    _attr_translation_key = "reported_humidity"
    _attr_name = "Reported humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "reported_humidity")

    @property
    def native_value(self) -> float | None:
        return self._bridge.reported_humidity

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "aggregation": self._bridge.hum_agg,
            "sources_total": len(self._bridge.hum_entities),
            "sources_available": self._bridge.hum_available,
        }


class PollCount(BridgeEntity, SensorEntity):
    """How many polls the master has made since startup."""

    _attr_translation_key = "poll_count"
    _attr_name = "Poll count"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "poll_count")

    @property
    def native_value(self) -> int:
        return self._bridge.poll_count


class LastPoll(BridgeEntity, SensorEntity):
    """Timestamp of the most recent poll answered."""

    _attr_translation_key = "last_poll"
    _attr_name = "Last poll"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "last_poll")

    @property
    def native_value(self):
        return self._bridge.last_poll
