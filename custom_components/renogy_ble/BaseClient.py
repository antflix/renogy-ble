
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

import asyncio
import configparser
import logging
import traceback
from .Utils import bytes_to_int, crc16_modbus, int_to_bytes
from .BLE import DeviceManager, Device
_LOGGER = logging.getLogger(__name__)
# Base class that works with all Renogy family devices
# Should be extended by each client with its own parsers and section definitions
# Section example: {'register': 5000, 'words': 8, 'parser': self.parser_func}

ALIAS_PREFIXES = ['BT-TH', 'RNGRBP', 'BTRIC']
NOTIFY_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID  = "0000ffd1-0000-1000-8000-00805f9b34fb"
READ_TIMEOUT = 20 # (seconds)
READ_SUCCESS = 3
READ_ERROR = 131

class BaseClient:
    def __init__(self, config):
        self.config: configparser.ConfigParser = config
        self.device = None
        self.poll_timer = None
        self.read_timeout = None
        self.data = {}
        self.device_id = self.config['device'].getint('device_id')
        self.sections = []
        self.section_index = 0
        self.loop = self._get_or_create_event_loop()  # Ensure the event loop is assigned here
        _LOGGER.info(f"Init {self.__class__.__name__}: {self.config['device']['alias']} => {self.config['device']['mac_addr']}")
        
    async def run(self):
        """Continuously discover, connect, and poll data every 10 seconds."""
        while True:
            try:
                self.manager = DeviceManager(
                    mac_address=self.config['device']['mac_addr'],
                    alias=self.config['device']['alias'],
                    adapter=self.config['device'].get('adapter', 'hci0')
                )
                await self.manager.discover()
                if not self.manager.device_found:
                    _LOGGER.warning("Device not found: %s", self.config['device']['mac_addr'])
                    await asyncio.sleep(10)
                    continue

                self.device = Device(
                    mac_address=self.config['device']['mac_addr'],
                    on_resolved=self.__on_resolved,
                    on_data=self.on_data_received,
                    on_connect_fail=self.__on_connect_fail,
                    notify_uuid=NOTIFY_CHAR_UUID,
                    write_uuid=WRITE_CHAR_UUID
                )
                await self.device.connect()

                # Initial read
                await self.read_section()

                # Loop and poll every 10 seconds
                while True:
                    await asyncio.sleep(10)
                    await self.read_section()
            except Exception as e:
                _LOGGER.error(f"[RUN LOOP] Exception: {e}")
                await self.disconnect()
                await asyncio.sleep(10)
                
    def _get_or_create_event_loop(self):
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def start(self):
        try:
            self.loop.create_task(self.connect())
        except Exception as e:
            logging.error(f"Failed to start BaseClient: {e}")
            self.__on_error(e)

    async def connect(self):
        self.manager = DeviceManager(mac_address=self.config['device']['mac_addr'], alias=self.config['device']['alias'])
        await self.manager.discover()
        if not self.manager.device_found:
            logging.error(f"Device not found: {self.config['device']['alias']} => {self.config['device']['mac_addr']}")
            return
        self.device = Device(
            mac_address=self.config['device']['mac_addr'],
            on_resolved=self.__on_resolved,
            on_data=self.on_data_received,
            on_connect_fail=self.__on_connect_fail,
            notify_uuid=NOTIFY_CHAR_UUID,
            write_uuid=WRITE_CHAR_UUID
        )
        await self.device.connect()

    async def disconnect(self):
        if self.device:
            await self.device.disconnect()

    async def on_data_received(self, response):
        if self.read_timeout and not self.read_timeout.cancelled(): self.read_timeout.cancel()
        operation = bytes_to_int(response, 1, 1)

        if operation == READ_SUCCESS or operation == READ_ERROR:
            if (operation == READ_SUCCESS and
                self.section_index < len(self.sections) and
                self.sections[self.section_index]['parser'] != None and
                self.sections[self.section_index]['words'] * 2 + 5 == len(response)):
                # call the parser and update data
                _LOGGER.info(f"on_data_received: read operation success")
                self.__safe_parser(self.sections[self.section_index]['parser'], response)
            else:
                _LOGGER.info(f"on_data_received: read operation failed: {response.hex()}")

            if self.section_index >= len(self.sections) - 1: # last section, read complete
                self.section_index = 0
                self.on_read_operation_complete()
                await self.check_polling()
            else:
                self.section_index += 1
                await asyncio.sleep(0.5)
                await self.read_section()
        else:
            logging.warning("on_data_received: unknown operation={}".format(operation))

    def on_read_operation_complete(self):
        _LOGGER.info("on_read_operation_complete")
        self.data['__device'] = self.config['device']['alias']
        self.data['__client'] = self.__class__.__name__
        self.__safe_callback(self.on_data_callback, self.data)

    def on_read_timeout(self):
        logging.error("on_read_timeout => Timed out! Please check your device_id!")
        self.stop()

    async def check_polling(self):
        if self.config.get('data', {}).get('enable_polling', False):
            await asyncio.sleep(self.config['data'].getint('poll_interval'))
            await self.read_section()

    async def read_section(self):
        # Reset data at the start of a full read cycle (section_index == 0)
        if self.section_index == 0:
            self.data = {}
        index = self.section_index
        if self.device_id is None or len(self.sections) == 0:
            return logging.error("BaseClient cannot be used directly")

        self.read_timeout = self.loop.call_later(READ_TIMEOUT, self.on_read_timeout)
        request = self.create_generic_read_request(self.device_id, 3, self.sections[index]['register'], self.sections[index]['words'])
        await self.device.characteristic_write_value(request)

    def __on_resolved(self):
        _LOGGER.info("resolved services")
        self.loop.create_task(self.read_section())

    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = None
        if regAddr != None and readWrd != None:
            data = []
            data.append(device_id)
            data.append(function)
            data.append(int_to_bytes(regAddr, 0))
            data.append(int_to_bytes(regAddr, 1))
            data.append(int_to_bytes(readWrd, 0))
            data.append(int_to_bytes(readWrd, 1))

            crc = crc16_modbus(bytes(data))
            data.append(crc[0])
            data.append(crc[1])
            logging.debug("{} {} => {}".format("create_request_payload", regAddr, data))
        return data

    def __on_error(self, error = None):
        logging.error(f"Exception occured: {error}")
        self.__safe_callback(self.on_error_callback, error)
        self.stop()

    def __on_connect_fail(self, error):
        logging.error(f"Connection failed: {error}")
        self.__safe_callback(self.on_error_callback, error)
        self.stop()

    def stop(self):
        if self.read_timeout and not self.read_timeout.cancelled(): self.read_timeout.cancel()
        self.loop.create_task(self.disconnect())

    def __safe_callback(self, calback, param):
        if calback is not None:
            try:
                calback(self, param)
            except Exception as e:
                logging.error(f"__safe_callback => exception in callback! {e}")
                traceback.print_exc()

    def __safe_parser(self, parser, param):
        if parser is not None:
            try:
                parser(param)
            except Exception as e:
                logging.error(f"exception in parser! {e}")
                traceback.print_exc()