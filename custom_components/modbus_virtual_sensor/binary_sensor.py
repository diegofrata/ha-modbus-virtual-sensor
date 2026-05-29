"""Binary sensor reporting the link to the RS485<->TCP bridge."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .bridge import ModbusVirtualSensorBridge
from .const import DOMAIN
from .entity import BridgeEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    bridge: ModbusVirtualSensorBridge = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ConnectionStatus(bridge)])


class ConnectionStatus(BridgeEntity, BinarySensorEntity):
    """On while the TCP connection to the bridge is established."""

    _attr_translation_key = "connection"
    _attr_name = "Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, bridge: ModbusVirtualSensorBridge) -> None:
        super().__init__(bridge, "connection")

    @property
    def is_on(self) -> bool:
        return self._bridge.connected
