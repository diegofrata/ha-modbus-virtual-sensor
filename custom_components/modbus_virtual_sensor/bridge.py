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
    CONF_HUM_AGGREGATION,
    CONF_HUM_REGISTER,
    CONF_HUM_SCALE,
    CONF_HUMIDITY_ENTITIES,
    CONF_IDLE_TIMEOUT,
    CONF_PORT,
    CONF_TEMP_AGGREGATION,
    CONF_TEMP_REGISTER,
    CONF_TEMP_SCALE,
    CONF_TEMP_SIGNED,
    CONF_TEMPERATURE_ENTITIES,
    CONF_UNIT,
    DEFAULT_AGGREGATION,
    DEFAULT_HUM_REGISTER,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SCALE,
    DEFAULT_TEMP_REGISTER,
    DEFAULT_TEMP_SIGNED,
    DEFAULT_UNIT,
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    SIGNAL_UPDATE,
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
        self.port: int = cfg.get(CONF_PORT, DEFAULT_PORT)
        self.unit: int = cfg.get(CONF_UNIT, DEFAULT_UNIT)
        self.temp_entities: list[str] = cfg.get(CONF_TEMPERATURE_ENTITIES, [])
        self.hum_entities: list[str] = cfg.get(CONF_HUMIDITY_ENTITIES, [])
        self.temp_agg: str = cfg.get(CONF_TEMP_AGGREGATION, DEFAULT_AGGREGATION)
        self.hum_agg: str = cfg.get(CONF_HUM_AGGREGATION, DEFAULT_AGGREGATION)
        self.temp_reg: int = cfg.get(CONF_TEMP_REGISTER, DEFAULT_TEMP_REGISTER)
        self.hum_reg: int = cfg.get(CONF_HUM_REGISTER, DEFAULT_HUM_REGISTER)
        self.temp_scale: int = cfg.get(CONF_TEMP_SCALE, DEFAULT_SCALE)
        self.hum_scale: int = cfg.get(CONF_HUM_SCALE, DEFAULT_SCALE)
        self.temp_signed: bool = cfg.get(CONF_TEMP_SIGNED, DEFAULT_TEMP_SIGNED)
        self.idle_timeout: float = cfg.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)

        # Diagnostics surfaced as entities
        self.connected = False
        self.poll_count = 0
        self.last_poll = None
        self.reported_temp: float | None = None
        self.reported_humidity: float | None = None
        self.temp_available = 0
        self.hum_available = 0

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
    def _read_humidity(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _read_temperature(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNAVAILABLE:
            return None
        try:
            value = float(state.state)
        except (ValueError, TypeError):
            return None
        # Normalise to Celsius so mixed-unit sources aggregate correctly.
        if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == UnitOfTemperature.FAHRENHEIT:
            value = TemperatureConverter.convert(
                value, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return value

    @callback
    def _compute_registers(self) -> dict[int, int]:
        """Aggregate current source values and render them as registers."""
        temps = [self._read_temperature(e) for e in self.temp_entities]
        hums = [self._read_humidity(e) for e in self.hum_entities]
        self.temp_available = sum(v is not None for v in temps)
        self.hum_available = sum(v is not None for v in hums)

        temp = aggregate(temps, self.temp_agg)
        hum = aggregate(hums, self.hum_agg)
        if temp is not None:
            self.reported_temp = round(temp, 1)
        if hum is not None:
            self.reported_humidity = round(hum, 1)

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
