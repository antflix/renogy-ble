import logging
# from .BaseClient import BaseClient
from .BaseShuntClient import BaseShuntClient as BaseClient
from .Utils import bytes_to_int, parse_temperature
_LOGGER = logging.getLogger(__name__)
# Read and parse BT-1 RS232 type bluetooth module connected to Renogy Rover/Wanderer/Adventurer
# series charge controllers. Also works with BT-2 RS485 module on Rover Elite, DC Charger etc.
# Does not support Communication Hub with multiple devices connected

FUNCTION = {
    3: "READ",
    6: "WRITE"
}


class ShuntClient(BaseClient):
    def __init__(self, config, on_data_callback=None, on_error_callback=None):
        super().__init__(config)
        logging.debug(msg="DEBUG Client")
        self.on_data_callback = on_data_callback
        self.on_error_callback = on_error_callback
        self.data = {}
        # self.sections = [
        #     {'register': 12, 'words': 8, 'parser': self.parse_device_info},
        #     {'register': 26, 'words': 1, 'parser': self.parse_device_address},
        #     {'register': 256, 'words': 34, 'parser': self.parse_chargin_info},
        #     {'register': 57348, 'words': 1, 'parser': self.parse_battery_type}
        # ]
        self.sections = [
            {'register': 256, 'words': 110, 'parser': self.parse_shunt_info}
        ]

    def on_data_received(self, response):
        operation = bytes_to_int(response, 1, 1)
        if operation == 6: # write operation
            self.on_write_operation_complete()
            self.data = {}
        else:
            # read is handled in base class
            super().on_data_received(response)

    def on_write_operation_complete(self):
        _LOGGER.info("on_write_operation_complete")
        if self.on_data_callback is not None:
            self.on_data_callback(self, self.data)

    def parse_shunt_info(self, bs):
        if len(bs) < 73:
            _LOGGER.warning(f"Skipping parse_shunt_info: buffer too short ({len(bs)} bytes)")
            return {}

        data = {}
        data['charge_battery_voltage'] = bytes_to_int(bs, 25, 3, scale = 0.001)
        data['starter_battery_voltage'] = bytes_to_int(bs, 30, 2, scale = 0.001)
        data['discharge_amps'] = bytes_to_int(bs, 21, 3, scale = 0.001, signed=True)
        data['discharge_watts'] = round((data['charge_battery_voltage'] * data['discharge_amps']), 2)
        data['state_of_charge'] = bytes_to_int(bs, 34, 2, scale=0.1)

        self.data.update(data)
        return data

    async def run(self):
        try:
            await super(ShuntClient, self).run()
        except AttributeError:
            _LOGGER.error("BaseClient has no run method. Cannot execute run().")
