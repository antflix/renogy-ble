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

DOMAIN = "renogy_ble"

SENSOR_TYPES = {
    # Shunt-specific sensors
    'charge_battery_voltage': ['Charge Battery Voltage', 'V'],
    'starter_battery_voltage': ['Starter Battery Voltage', 'V'],
    'discharge_amps': ['Discharge Amps', 'A'],
    'discharge_watts': ['Discharge Watts', 'W'],
    'state_of_charge': ['State of Charge', '%'],
}

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Renogy BLE sensors."""
    if discovery_info is None:
        logging.error("No discovery information provided.")
        return

    sensors = []
    alias = discovery_info.get('alias')
    mac_addr = discovery_info.get('mac_addr')
    for sensor_type in SENSOR_TYPES:
        sensors.append(RenogyBLESensor(sensor_type, alias, mac_addr))

    add_entities(sensors, True)
    hass.data[DOMAIN]['entities'] = sensors
    logging.info("Renogy BLE sensors set up successfully.")

class RenogyBLESensor(Entity):
    """Representation of a Renogy BLE sensor."""

    def __init__(self, sensor_type, device_name, mac_addr):
        self._sensor_type = sensor_type
        self._name = f"{device_name or mac_addr} {SENSOR_TYPES[sensor_type][0]}"
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._state = "unavailable"
        self._mac_addr = mac_addr

        # guard missing device_name by falling back to MAC
        base = device_name or mac_addr
        safe = base.lower().replace('-', '').replace(' ', '_')
        self.entity_id = f"sensor.{safe}_{sensor_type}"

        logging.info(f"Initialized sensor {self._name}")

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def attributes(self):
        """Return the sensor attributes."""
        return {
            "unit_of_measurement": self._unit_of_measurement,
            "mac_address": self._mac_addr,
        }
    @property
    def available(self):
        """Return True if the sensor is available."""
        return self._state != "unavailable"

    @property
    def device_class(self):
        """Return the device class for UI representation."""
        if "voltage" in self._sensor_type:
            return "voltage"
        elif "amps" in self._sensor_type:
            return "current"
        elif "watts" in self._sensor_type:
            return "power"
        elif "state_of_charge" in self._sensor_type:
            return "battery"
        return None
    def update(self):
        """Update the sensor state."""
        pass

def update_sensors(hass, data):
    """Update the sensors with new data."""
    for entity in hass.data.get(DOMAIN, {}).get('entities', []):
        new_state = data.get(entity._sensor_type)
        # Only update sensors for which we have new data
        if new_state is None:
            continue
        entity._state = new_state
        # Schedule HA state update on main thread
        hass.loop.call_soon_threadsafe(
            hass.states.async_set,
            entity.entity_id,
            new_state,
            entity.attributes
        )
        logging.info(f"Updated sensor: {entity._name} with state: {new_state}")