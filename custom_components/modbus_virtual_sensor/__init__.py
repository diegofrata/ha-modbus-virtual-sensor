"""The Modbus Virtual Sensor integration.

Aggregates Home Assistant temperature/humidity sensors and serves the result to
a polling Modbus master over an RS485<->TCP bridge (e.g. an Elfin EW11) — i.e.
Home Assistant acting as a Modbus slave/server, which the built-in `modbus`
integration (master-only) cannot do.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bridge import ModbusVirtualSensorBridge
from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Modbus Virtual Sensor from a config entry."""
    bridge = ModbusVirtualSensorBridge(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = bridge

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    bridge.start()

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change (entity list, aggregation, registers, …)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and stop its responder."""
    bridge: ModbusVirtualSensorBridge | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if bridge is not None:
        await bridge.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
