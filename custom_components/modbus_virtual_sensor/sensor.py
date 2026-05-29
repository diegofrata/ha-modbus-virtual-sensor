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
            ActiveZone(bridge),
            PollCount(bridge),
            LastPoll(bridge),
        ]
    )


class _ZoneStatsMixin:
    """Shared 'how many zones contributed' attributes."""

    def _zone_stats(self) -> dict:
        return {
            "strategy": self._bridge.strategy,
            "zones_total": len(self._bridge.zones),
            "zones_available": self._bridge.zones_available,
            "active_zone": self._bridge.active_zone,
        }


class ReportedTemperature(_ZoneStatsMixin, BridgeEntity, SensorEntity):
    """The temperature served to the master."""

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
        b = self._bridge
        return {
            **self._zone_stats(),
            "register": b.temp_reg,
            "scale": b.temp_scale,
            "register_value": b.reg_values.get(b.temp_reg),
        }


class ReportedHumidity(_ZoneStatsMixin, BridgeEntity, SensorEntity):
    """The humidity served to the master."""

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
        b = self._bridge
        return {
            **self._zone_stats(),
            "register": b.hum_reg,
            "scale": b.hum_scale,
            "register_value": b.reg_values.get(b.hum_reg),
        }


class ActiveZone(BridgeEntity, SensorEntity):
    """Which zone (or aggregation) is currently driving the reported values."""

    _attr_translation_key = "active_zone"
    _attr_name = "Active zone"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "active_zone")

    @property
    def native_value(self) -> str | None:
        return self._bridge.active_zone


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
