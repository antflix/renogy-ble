# pylint: disable=missing-function-docstring, missing-class-docstring, missing-module-docstring
"""
This file is part of renogy_ble.

renogy_ble is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

renogy_ble is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with renogy_ble. If not, see <https://www.gnu.org/licenses/>.
"""
import logging
_LOGGER = logging.getLogger(__name__)

from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

SENSOR_TYPES = {
    'charge_battery_voltage': ['Charge Battery Voltage', 'V'],
    'starter_battery_voltage': ['Starter Battery Voltage', 'V'],
    'discharge_amps': ['Discharge Amps', 'A'],
    'discharge_watts': ['Discharge Watts', 'W'],
    'state_of_charge': ['State of Charge', '%'],
}

# List of current sensor entities
ENTITIES = []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities
) -> None:
    """Set up Renogy BLE sensors from a config entry."""
    conf = entry.data
    alias = conf.get("alias")
    mac = conf.get("mac")

    entities = [
        RenogyBLESensor(sensor_type, alias, mac)
        for sensor_type in SENSOR_TYPES
    ]
    async_add_entities(entities, True)

    # Keep track for updates/unload
    hass.data.setdefault(DOMAIN, {}).setdefault("entities", []).extend(entities)
    ENTITIES.extend(entities)


class RenogyBLESensor(Entity):
    """Representation of a single Renogy BLE sensor."""

    def __init__(self, sensor_type: str, device_name: str, mac_addr: str):
        self._sensor_type = sensor_type
        self._name = f"{device_name or mac_addr} {SENSOR_TYPES[sensor_type][0]}"
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._state = "unavailable"
        self._mac_addr = mac_addr

        # Build a safe entity_id, e.g. sensor.mydevice_charge_battery_voltage
        base = (device_name or mac_addr).lower().replace('-', '').replace(' ', '_')
        self.entity_id = f"sensor.{base}_{sensor_type}"
        self._attr_unique_id = self.entity_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return self._unit_of_measurement

    @property
    def attributes(self) -> dict:
        return {
            "unit_of_measurement": self._unit_of_measurement,
            "mac_address": self._mac_addr,
        }

    @property
    def available(self) -> bool:
        return self._state != "unavailable"

    @property
    def device_class(self):
        if "voltage" in self._sensor_type:
            return "voltage"
        if "amps" in self._sensor_type:
            return "current"
        if "watts" in self._sensor_type:
            return "power"
        if "state_of_charge" in self._sensor_type:
            return "battery"
        return None

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    def update(self):
        """Called by Home Assistant to refresh state; we do nothing."""
        pass


def update_sensors(data: dict) -> None:
    """Push new BLE data into each sensor and schedule a state update."""
    for entity in ENTITIES:
        new_state = data.get(entity._sensor_type)
        if new_state is None:
            continue
        entity._state = new_state
        entity.schedule_update_ha_state()