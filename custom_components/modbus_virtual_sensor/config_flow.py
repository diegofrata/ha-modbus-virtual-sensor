"""Config and options flow for Modbus Virtual Sensor."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADD_ANOTHER,
    CONF_HOST,
    CONF_HUM_REGISTER,
    CONF_HUM_SCALE,
    CONF_HUMIDITY_ENTITY,
    CONF_IDLE_TIMEOUT,
    CONF_MAX_AGE,
    CONF_NAME,
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
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCALE,
    DEFAULT_STRATEGY,
    DEFAULT_TEMP_REGISTER,
    DEFAULT_TEMP_SIGNED,
    DEFAULT_UNIT,
    DOMAIN,
    STRATEGIES,
)


def _temperature_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
    )


def _humidity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
    )


def _strategy_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=STRATEGIES,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="strategy",
        )
    )


def _zone_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_ZONE_NAME, default=""): str,
            vol.Required(CONF_TEMPERATURE_ENTITY): _temperature_selector(),
            vol.Required(CONF_HUMIDITY_ENTITY): _humidity_selector(),
            vol.Required(CONF_ADD_ANOTHER, default=False): bool,
        }
    )


class ModbusVirtualSensorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: connection target, then one or more zone pairs."""

    VERSION = 2

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zones: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_HOST: user_input[CONF_HOST],
                CONF_PORT: int(user_input[CONF_PORT]),
                CONF_UNIT: int(user_input[CONF_UNIT]),
            }
            await self.async_set_unique_id(
                f"{self._data[CONF_HOST]}:{self._data[CONF_PORT]}:{self._data[CONF_UNIT]}"
            )
            self._abort_if_unique_id_configured()
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Required(CONF_UNIT, default=DEFAULT_UNIT): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._zones.append(
                {
                    CONF_ZONE_NAME: user_input.get(CONF_ZONE_NAME, "").strip(),
                    CONF_TEMPERATURE_ENTITY: user_input[CONF_TEMPERATURE_ENTITY],
                    CONF_HUMIDITY_ENTITY: user_input[CONF_HUMIDITY_ENTITY],
                }
            )
            if user_input.get(CONF_ADD_ANOTHER):
                return await self.async_step_zone()
            self._data[CONF_ZONES] = self._zones
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(),
            description_placeholders={"count": str(len(self._zones))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ModbusVirtualSensorOptionsFlow(config_entry)


class ModbusVirtualSensorOptionsFlow(OptionsFlow):
    """Edit the aggregation strategy, register mapping and robustness settings.

    (Zones are edited by removing and re-adding the integration in v0.2.0.)
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        cur = {**self._entry.data, **self._entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_STRATEGY, default=cur.get(CONF_STRATEGY, DEFAULT_STRATEGY)
                ): _strategy_selector(),
                vol.Required(
                    CONF_TEMP_REGISTER,
                    default=cur.get(CONF_TEMP_REGISTER, DEFAULT_TEMP_REGISTER),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_HUM_REGISTER,
                    default=cur.get(CONF_HUM_REGISTER, DEFAULT_HUM_REGISTER),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_TEMP_SCALE, default=cur.get(CONF_TEMP_SCALE, DEFAULT_SCALE)
                ): vol.Coerce(int),
                vol.Required(
                    CONF_HUM_SCALE, default=cur.get(CONF_HUM_SCALE, DEFAULT_SCALE)
                ): vol.Coerce(int),
                vol.Required(
                    CONF_TEMP_SIGNED,
                    default=cur.get(CONF_TEMP_SIGNED, DEFAULT_TEMP_SIGNED),
                ): bool,
                vol.Required(
                    CONF_IDLE_TIMEOUT,
                    default=cur.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_MAX_AGE, default=cur.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
