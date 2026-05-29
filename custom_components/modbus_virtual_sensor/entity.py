"""Shared base entity for Modbus Virtual Sensor."""
from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .bridge import ModbusVirtualSensorBridge
from .const import DOMAIN


class BridgeEntity(Entity):
    """Base entity bound to a bridge; refreshes on the bridge's dispatcher signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, bridge: ModbusVirtualSensorBridge, key: str) -> None:
        self._bridge = bridge
        self._attr_unique_id = f"{bridge.entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._bridge.entry.entry_id)},
            name=self._bridge.entry.title,
            manufacturer="Modbus Virtual Sensor",
            model=f"Modbus slave #{self._bridge.unit} @ {self._bridge.host}:{self._bridge.port}",
            configuration_url=f"http://{self._bridge.host}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._bridge.signal_update, self.async_write_ha_state
            )
        )
