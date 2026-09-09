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
    CONF_HUM_OFFSET,
    CONF_HUM_REGISTER,
    CONF_HUM_SCALE,
    CONF_HUMIDITY_ENTITY,
    CONF_IDLE_TIMEOUT,
    CONF_MAX_AGE,
    CONF_NAME,
    CONF_PORT,
    CONF_STRATEGY,
    CONF_TEMP_OFFSET,
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
    DEFAULT_OFFSET,
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


def _zone_schema(*, add_another: bool = True) -> vol.Schema:
    fields: dict = {
        vol.Optional(CONF_ZONE_NAME, default=""): str,
        vol.Required(CONF_TEMPERATURE_ENTITY): _temperature_selector(),
        vol.Required(CONF_HUMIDITY_ENTITY): _humidity_selector(),
    }
    if add_another:
        fields[vol.Required(CONF_ADD_ANOTHER, default=False)] = bool
    return vol.Schema(fields)


def _zone_from_input(user_input: dict[str, Any]) -> dict:
    return {
        CONF_ZONE_NAME: user_input.get(CONF_ZONE_NAME, "").strip(),
        CONF_TEMPERATURE_ENTITY: user_input[CONF_TEMPERATURE_ENTITY],
        CONF_HUMIDITY_ENTITY: user_input[CONF_HUMIDITY_ENTITY],
    }


def _zone_label(index: int, zone: dict) -> str:
    """Human-readable label for a zone in the remove list."""
    pair = f"{zone[CONF_TEMPERATURE_ENTITY]} + {zone[CONF_HUMIDITY_ENTITY]}"
    name = zone.get(CONF_ZONE_NAME) or f"Zone {index + 1}"
    return f"{name} ({pair})"


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
            self._zones.append(_zone_from_input(user_input))
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
    """Options: a menu to edit settings, add a zone, or remove zones.

    Settings (strategy, registers, scaling, offsets, timeouts) are stored in
    ``entry.options``. Zones live in ``entry.data`` (they were captured during
    setup), so adding/removing a zone updates the entry data directly; the
    integration's update listener then reloads it.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    @property
    def _zones(self) -> list[dict]:
        return list(self._entry.data.get(CONF_ZONES, []))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["settings", "add_zone"]
        if len(self._zones) > 1:
            options.append("remove_zone")
        return self.async_show_menu(
            step_id="init",
            menu_options=options,
            description_placeholders={"count": str(len(self._zones))},
        )

    async def async_step_settings(
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
                    CONF_TEMP_OFFSET,
                    default=cur.get(CONF_TEMP_OFFSET, DEFAULT_OFFSET),
                ): vol.Coerce(float),
                vol.Required(
                    CONF_HUM_OFFSET, default=cur.get(CONF_HUM_OFFSET, DEFAULT_OFFSET)
                ): vol.Coerce(float),
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
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            zones = [*self._zones, _zone_from_input(user_input)]
            return self._save_zones(zones)

        return self.async_show_form(
            step_id="add_zone",
            data_schema=_zone_schema(add_another=False),
            description_placeholders={"count": str(len(self._zones))},
        )

    async def async_step_remove_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        zones = self._zones
        errors: dict[str, str] = {}
        if user_input is not None:
            remove = {int(i) for i in user_input.get("zones", [])}
            remaining = [z for i, z in enumerate(zones) if i not in remove]
            if not remaining:
                errors["zones"] = "at_least_one"
            elif not remove:
                return await self.async_step_init()
            else:
                return self._save_zones(remaining)

        schema = vol.Schema(
            {
                vol.Optional("zones", default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=str(i), label=_zone_label(i, z)
                            )
                            for i, z in enumerate(zones)
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="remove_zone", data_schema=schema, errors=errors
        )

    def _save_zones(self, zones: list[dict]) -> ConfigFlowResult:
        """Write the new zone list to entry data and finish the flow.

        Updating ``data`` fires the entry's update listener (reload). Finishing
        with the unchanged options doesn't trigger a second reload.
        """
        self.hass.config_entries.async_update_entry(
            self._entry, data={**self._entry.data, CONF_ZONES: zones}
        )
        return self.async_create_entry(title="", data=dict(self._entry.options))
