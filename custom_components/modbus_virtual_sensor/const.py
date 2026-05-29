"""Constants for the Modbus Virtual Sensor integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "modbus_virtual_sensor"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

# --- Config / option keys ---
CONF_NAME = "name"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT = "unit"
CONF_TEMPERATURE_ENTITIES = "temperature_entities"
CONF_HUMIDITY_ENTITIES = "humidity_entities"
CONF_TEMP_AGGREGATION = "temp_aggregation"
CONF_HUM_AGGREGATION = "hum_aggregation"
CONF_TEMP_REGISTER = "temp_register"
CONF_HUM_REGISTER = "hum_register"
CONF_TEMP_SCALE = "temp_scale"
CONF_HUM_SCALE = "hum_scale"
CONF_TEMP_SIGNED = "temp_signed"
CONF_IDLE_TIMEOUT = "idle_timeout"

# --- Defaults (generic; the dehumidifier example uses unit 13, regs 0/1) ---
DEFAULT_NAME = "Modbus Virtual Sensor"
DEFAULT_PORT = 8899          # common RS485<->TCP bridge port (e.g. Elfin EW11)
DEFAULT_UNIT = 1             # Modbus slave address this responder answers as
DEFAULT_HUM_REGISTER = 0
DEFAULT_TEMP_REGISTER = 1
DEFAULT_SCALE = 10           # 0.1 resolution -> value * 10
DEFAULT_TEMP_SIGNED = True   # temperature may go negative
DEFAULT_IDLE_TIMEOUT = 0     # 0 = rely on TCP keepalive only
DEFAULT_AGGREGATION = "mean"

AGGREGATIONS = ["mean", "median", "min", "max"]

# --- Reconnect tuning ---
RECONNECT_BASE_DELAY = 3
RECONNECT_MAX_DELAY = 30

# --- Dispatcher signal prefix (per-entry suffix appended at runtime) ---
SIGNAL_UPDATE = f"{DOMAIN}_update"
