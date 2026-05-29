"""The async Modbus-slave responder that serves aggregated HA sensor values."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import socket

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

from .calc import aggregate
from .const import (
    CONF_HOST,
    CONF_HUM_REGISTER,
    CONF_HUM_SCALE,
    CONF_HUMIDITY_ENTITY,
    CONF_IDLE_TIMEOUT,
    CONF_MAX_AGE,
    CONF_PORT,
    CONF_STRATEGY,
    CONF_TEMP_REGISTER,
    CONF_TEMP_SCALE,
    CONF_TEMP_SIGNED,
    CONF_TEMPERATURE_ENTITY,
    CONF_UNIT,
    CONF_ZONE_NAME,
    CONF_ZONES,
    DEFAULT_HUM_REGISTER,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MAX_AGE,
    DEFAULT_PORT,
    DEFAULT_SCALE,
    DEFAULT_STRATEGY,
    DEFAULT_TEMP_REGISTER,
    DEFAULT_TEMP_SIGNED,
    DEFAULT_UNIT,
    HUM_MAX,
    HUM_MIN,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    SIGNAL_UPDATE,
    STRATEGY_MEDIAN,
    STRATEGY_WETTEST,
    TEMP_MAX,
    TEMP_MIN,
)
from .modbus_rtu import build_read_response, take_request, to_register

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = (None, "", "unknown", "unavailable")


class ModbusVirtualSensorBridge:
    """Holds one config entry's connection, state and the responder task."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        cfg = {**entry.data, **entry.options}

        self.host: str = cfg[CONF_HOST]
        self.port: int = int(cfg.get(CONF_PORT, DEFAULT_PORT))
        self.unit: int = int(cfg.get(CONF_UNIT, DEFAULT_UNIT))
        self.zones: list[dict] = cfg.get(CONF_ZONES, [])
        self.strategy: str = cfg.get(CONF_STRATEGY, DEFAULT_STRATEGY)
        self.temp_reg: int = int(cfg.get(CONF_TEMP_REGISTER, DEFAULT_TEMP_REGISTER))
        self.hum_reg: int = int(cfg.get(CONF_HUM_REGISTER, DEFAULT_HUM_REGISTER))
        self.temp_scale: int = int(cfg.get(CONF_TEMP_SCALE, DEFAULT_SCALE))
        self.hum_scale: int = int(cfg.get(CONF_HUM_SCALE, DEFAULT_SCALE))
        self.temp_signed: bool = cfg.get(CONF_TEMP_SIGNED, DEFAULT_TEMP_SIGNED)
        self.idle_timeout: float = float(cfg.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT))
        self.max_age: float = float(cfg.get(CONF_MAX_AGE, DEFAULT_MAX_AGE))

        # Diagnostics surfaced as entities
        self.connected = False
        self.poll_count = 0
        self.last_poll = None
        self.reported_temp: float | None = None
        self.reported_humidity: float | None = None
        self.active_zone: str | None = None
        self.zones_available = 0

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def signal_update(self) -> str:
        return f"{SIGNAL_UPDATE}_{self.entry.entry_id}"

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal_update)

    # --- lifecycle -------------------------------------------------------
    def start(self) -> None:
        self._task = self.hass.async_create_background_task(
            self._run(), name=f"{self.entry.title} modbus responder"
        )

    async def async_stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    # --- source reading & aggregation ------------------------------------
    def _fresh_state(self, entity_id: str):
        """Return the state if present, available and (optionally) not stale."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE:
            return None
        if self.max_age:
            last = getattr(state, "last_reported", None) or state.last_updated
            if last is not None and (dt_util.utcnow() - last).total_seconds() > self.max_age:
                return None
        return state

    def _read_humidity(self, entity_id: str) -> float | None:
        state = self._fresh_state(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        return value if HUM_MIN <= value <= HUM_MAX else None

    def _read_temperature(self, entity_id: str) -> float | None:
        state = self._fresh_state(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT:
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return value if TEMP_MIN <= value <= TEMP_MAX else None

    @callback
    def _compute_registers(self) -> dict[int, int]:
        """Read every zone, apply the strategy, and render Modbus registers."""
        readings = []  # (zone_name, temperature_c, humidity)
        for zone in self.zones:
            temp = self._read_temperature(zone[CONF_TEMPERATURE_ENTITY])
            hum = self._read_humidity(zone[CONF_HUMIDITY_ENTITY])
            if temp is None or hum is None:
                continue  # only fully-valid zones contribute a matched pair
            name = zone.get(CONF_ZONE_NAME) or zone[CONF_HUMIDITY_ENTITY]
            readings.append((name, temp, hum))
        self.zones_available = len(readings)

        if readings:
            if self.strategy == STRATEGY_WETTEST:
                name, temp, hum = max(readings, key=lambda r: r[2])
                self.active_zone = name
            else:
                method = STRATEGY_MEDIAN if self.strategy == STRATEGY_MEDIAN else "mean"
                temp = aggregate([r[1] for r in readings], method)
                hum = aggregate([r[2] for r in readings], method)
                self.active_zone = f"{method} of {len(readings)} zones"
            self.reported_temp = round(temp, 1)
            self.reported_humidity = round(hum, 1)
        # else: hold the last good values (don't feed garbage when all drop out)

        regs: dict[int, int] = {}
        if self.reported_temp is not None:
            try:
                regs[self.temp_reg] = to_register(
                    self.reported_temp, self.temp_scale, self.temp_signed
                )
            except ValueError as err:
                _LOGGER.warning("Temperature out of range: %s", err)
        if self.reported_humidity is not None:
            try:
                regs[self.hum_reg] = to_register(self.reported_humidity, self.hum_scale, False)
            except ValueError as err:
                _LOGGER.warning("Humidity out of range: %s", err)
        return regs

    # --- networking ------------------------------------------------------
    @staticmethod
    def _enable_keepalive(writer: asyncio.StreamWriter) -> None:
        """Detect silently-dead links (Wi-Fi drop, bridge reboot) at the OS level."""
        sock = writer.get_extra_info("socket")
        if sock is None:
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 20)
            elif hasattr(socket, "TCP_KEEPALIVE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 20)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except OSError:
            pass  # best-effort; the reconnect loop still covers us

    async def _run(self) -> None:
        delay = RECONNECT_BASE_DELAY
        while not self._stop.is_set():
            healthy = False
            writer: asyncio.StreamWriter | None = None
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                self._enable_keepalive(writer)
                self.connected = True
                self._notify()
                _LOGGER.info("Connected to %s:%s as Modbus slave #%s",
                             self.host, self.port, self.unit)
                healthy = await self._serve(reader, writer)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # never let the responder task die
                _LOGGER.warning("Modbus bridge %s:%s connection problem: %s",
                                self.host, self.port, err)
            finally:
                if self.connected:
                    self.connected = False
                    self._notify()
                if writer is not None:
                    writer.close()

            if self._stop.is_set():
                break
            if healthy:
                delay = RECONNECT_BASE_DELAY  # link worked -> reconnect promptly
            _LOGGER.debug("Reconnecting in %ss", delay)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            if not healthy:  # still down -> back off (capped)
                delay = min(RECONNECT_MAX_DELAY, max(delay, 1) * 2)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """Answer polls until the peer closes or the link breaks. True if data seen."""
        buf = bytearray()
        received = False
        while not self._stop.is_set():
            try:
                if self.idle_timeout:
                    data = await asyncio.wait_for(reader.read(256), timeout=self.idle_timeout)
                else:
                    data = await reader.read(256)
            except asyncio.TimeoutError:
                _LOGGER.debug("No poll for %ss; recycling connection", self.idle_timeout)
                return received
            if not data:
                _LOGGER.debug("Peer closed the connection")
                return received

            received = True
            buf += data
            responded = False
            while (req := take_request(buf)) is not None:
                if req["unit"] != self.unit:
                    continue  # another slave's frame; ignore
                regs = self._compute_registers()
                writer.write(build_read_response(self.unit, req["start"], req["qty"], regs))
                responded = True
                self.poll_count += 1
                self.last_poll = dt_util.utcnow()
            if responded:
                await writer.drain()
                self._notify()
        return received
