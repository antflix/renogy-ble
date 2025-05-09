# pylint: disable=missing-function-docstring, missing-class-docstring, missing-module-docstring
import logging
import asyncio
from homeassistant.core import HomeAssistant
from .sensor import RenogyBLESensor, update_sensors
from .ShuntClient import ShuntClient
from .Utils import *
from . import utils as Utils
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
_LOGGER = logging.getLogger(__name__)

DOMAIN = "renogy_ble"
    # 'battery_percentage': ['Battery Percentage', '%'],
    # 'battery_voltage': ['Battery Voltage', 'V'],
    # 'battery_current': ['Battery Current', 'A'],
    # 'battery_temperature': ['Battery Temperature', '°C'],
    # 'controller_temperature': ['Controller Temperature', '°C'],
    # 'load_status': ['Load Status', None],
    # 'load_voltage': ['Load Voltage', 'V'],
    # 'load_current': ['Load Current', 'A'],
    # 'load_power': ['Load Power', 'W'],
    # 'pv_voltage': ['PV Voltage', 'V'],
    # 'pv_current': ['PV Current', 'A'],
    # 'pv_power': ['PV Power', 'W'],
    # 'max_charging_power_today': ['Max Charging Power Today', 'W'],
    # 'max_discharging_power_today': ['Max Discharging Power Today', 'W'],
    # 'charging_amp_hours_today': ['Charging Amp Hours Today', 'Ah'],
    # 'discharging_amp_hours_today': ['Discharging Amp Hours Today', 'Ah'],
    # 'power_generation_today': ['Power Generation Today', 'Wh'],
    # 'power_consumption_today': ['Power Consumption Today', 'Wh'],
    # 'power_generation_total': ['Power Generation Total', 'Wh'],
    # 'charging_status': ['Charging Status', None],
    # 'battery_type': ['Battery Type', None],
SENSOR_TYPES = {
    'charge_battery_voltage': ['Charge Battery Voltage', 'V'],
    'starter_battery_voltage': ['Starter Battery Voltage', 'V'],
    'discharge_amps': ['Discharge Amps', 'A'],
    'discharge_watts': ['Discharge Watts', 'W'],
    'state_of_charge': ['State of Charge', '%'],
}

async def async_setup_entry(hass, entry):
    if DOMAIN in hass.data:
        _LOGGER.warning("Renogy BLE already set up. Skipping duplicate setup.")
        return False
    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]['entities'] = []
    logging.info("Renogy BLE entry setup")
    return True

async def async_setup(hass: HomeAssistant, haconfig: dict):
    """Set up Renogy BLE from YAML config."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN]['entities'] = []

    # Read configuration from YAML
    conf = haconfig.get(DOMAIN, {})
    devices = conf.get('devices', [])
    if not devices:
        _LOGGER.error("No devices configured under renogy_ble.devices")
        return False

    # Create sensor entities and register initial states
    sensors = []
    for device_cfg in devices:
        alias = device_cfg.get('alias')
        mac = device_cfg.get('mac_addr')
        for sensor_type in SENSOR_TYPES:
            sensor = RenogyBLESensor(sensor_type, alias, mac)
            sensors.append(sensor)
            hass.states.async_set(sensor.entity_id, sensor.state, sensor.attributes)
    hass.data[DOMAIN]['entities'] = sensors
    logging.info("Renogy BLE sensors set up successfully.")

    # Define callbacks
    def on_data_received(client, data):
        filtered = Utils.filter_fields(data, conf.get('fields', []))
        logging.info(f"{client.alias or client.mac} => {filtered}")
        if not conf.get('enable_polling', True):
            client.disconnect()
        update_sensors(hass, filtered)

    def on_error(client, error):
        _LOGGER.error(f"BLE client error: {error}")
        update_sensors(hass, {})

    # Connection coroutine
    async def connect_client(cfg):
        client_cls = ShuntClient
        client = client_cls(cfg, on_data_received, on_error)
        while True:
            try:
                await hass.async_add_executor_job(client.connect)
                return
            except Exception as e:
                _LOGGER.error(f"Client connection failed: {e}. Retrying in 5 seconds...")
                update_sensors(hass, {})
                await asyncio.sleep(5)

    # Schedule connection after HA startup
    for device_cfg in devices:
        def schedule_connect(event, cfg=device_cfg):
            hass.loop.call_soon_threadsafe(
                hass.async_create_task,
                connect_client(cfg)
            )
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, schedule_connect)

    return True