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
CONF_ZONES = "zones"
CONF_ZONE_NAME = "zone_name"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_ADD_ANOTHER = "add_another"
CONF_STRATEGY = "strategy"
CONF_TEMP_REGISTER = "temp_register"
CONF_HUM_REGISTER = "hum_register"
CONF_TEMP_SCALE = "temp_scale"
CONF_HUM_SCALE = "hum_scale"
CONF_TEMP_OFFSET = "temp_offset"
CONF_HUM_OFFSET = "hum_offset"
CONF_TEMP_SIGNED = "temp_signed"
CONF_IDLE_TIMEOUT = "idle_timeout"
CONF_MAX_AGE = "max_age"

# Legacy keys (v1 entries) — only referenced by async_migrate_entry
CONF_TEMPERATURE_ENTITIES = "temperature_entities"
CONF_HUMIDITY_ENTITIES = "humidity_entities"

# --- Aggregation strategies ---
# wettest: report the matched (T, RH) of the zone with the highest RH — the
#          worst-case choice for a dehumidifier (keep every room below target).
# mean/median: aggregate temperature and humidity across zones independently.
STRATEGY_WETTEST = "wettest"
STRATEGY_MEAN = "mean"
STRATEGY_MEDIAN = "median"
STRATEGIES = [STRATEGY_WETTEST, STRATEGY_MEAN, STRATEGY_MEDIAN]
DEFAULT_STRATEGY = STRATEGY_WETTEST

# --- Plausibility bounds (internal; readings outside are ignored) ---
HUM_MIN, HUM_MAX = 0.0, 100.0
TEMP_MIN, TEMP_MAX = -50.0, 100.0

# --- Defaults (generic; the dehumidifier example uses unit 13, regs 0/1) ---
DEFAULT_NAME = "Modbus Virtual Sensor"
DEFAULT_PORT = 8899          # common RS485<->TCP bridge port (e.g. Elfin EW11)
DEFAULT_UNIT = 1             # Modbus slave address this responder answers as
DEFAULT_HUM_REGISTER = 0
DEFAULT_TEMP_REGISTER = 1
DEFAULT_SCALE = 10           # 0.1 resolution -> value * 10
DEFAULT_OFFSET = 0.0         # calibration added to the value before sending
DEFAULT_TEMP_SIGNED = True   # temperature may go negative
DEFAULT_IDLE_TIMEOUT = 0     # 0 = rely on TCP keepalive only
DEFAULT_MAX_AGE = 0          # 0 = don't treat stale sensors as unavailable

# --- Reconnect tuning ---
RECONNECT_BASE_DELAY = 3
RECONNECT_MAX_DELAY = 30

# --- Dispatcher signal prefix (per-entry suffix appended at runtime) ---
SIGNAL_UPDATE = f"{DOMAIN}_update"
