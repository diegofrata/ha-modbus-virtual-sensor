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
    AGGREGATIONS,
    CONF_HOST,
    CONF_HUM_AGGREGATION,
    CONF_HUM_REGISTER,
    CONF_HUM_SCALE,
    CONF_HUMIDITY_ENTITIES,
    CONF_IDLE_TIMEOUT,
    CONF_NAME,
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
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCALE,
    DEFAULT_TEMP_REGISTER,
    DEFAULT_TEMP_SIGNED,
    DEFAULT_UNIT,
    DOMAIN,
)


def _temperature_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor", device_class="temperature", multiple=True
        )
    )


def _humidity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor", device_class="humidity", multiple=True
        )
    )


def _aggregation_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=AGGREGATIONS,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="aggregation",
        )
    )


class ModbusVirtualSensorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: connection target and the source sensors."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_UNIT]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Required(CONF_UNIT, default=DEFAULT_UNIT): vol.Coerce(int),
                vol.Required(CONF_TEMPERATURE_ENTITIES): _temperature_selector(),
                vol.Required(CONF_HUMIDITY_ENTITIES): _humidity_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ModbusVirtualSensorOptionsFlow(config_entry)


class ModbusVirtualSensorOptionsFlow(OptionsFlow):
    """Edit sources, aggregation method and the register mapping after setup."""

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
                    CONF_TEMPERATURE_ENTITIES,
                    default=cur.get(CONF_TEMPERATURE_ENTITIES, []),
                ): _temperature_selector(),
                vol.Required(
                    CONF_HUMIDITY_ENTITIES,
                    default=cur.get(CONF_HUMIDITY_ENTITIES, []),
                ): _humidity_selector(),
                vol.Required(
                    CONF_TEMP_AGGREGATION,
                    default=cur.get(CONF_TEMP_AGGREGATION, DEFAULT_AGGREGATION),
                ): _aggregation_selector(),
                vol.Required(
                    CONF_HUM_AGGREGATION,
                    default=cur.get(CONF_HUM_AGGREGATION, DEFAULT_AGGREGATION),
                ): _aggregation_selector(),
                vol.Required(
                    CONF_TEMP_REGISTER,
                    default=cur.get(CONF_TEMP_REGISTER, DEFAULT_TEMP_REGISTER),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_HUM_REGISTER,
                    default=cur.get(CONF_HUM_REGISTER, DEFAULT_HUM_REGISTER),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_TEMP_SCALE,
                    default=cur.get(CONF_TEMP_SCALE, DEFAULT_SCALE),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_HUM_SCALE,
                    default=cur.get(CONF_HUM_SCALE, DEFAULT_SCALE),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_TEMP_SIGNED,
                    default=cur.get(CONF_TEMP_SIGNED, DEFAULT_TEMP_SIGNED),
                ): bool,
                vol.Required(
                    CONF_IDLE_TIMEOUT,
                    default=cur.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
