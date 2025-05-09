
import os
import logging
import configparser
import asyncio
from .Utils import bytes_to_int, int_to_bytes, crc16_modbus
from .BLE import DeviceManager, Device
from bleak import BleakClient
_LOGGER = logging.getLogger(__name__)
ALIAS_PREFIX = 'RMTShunt300'
ALIAS_PREFIX_PRO = 'Shunt300'
NOTIFY_CHAR_UUID = "0000c411-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID  = ""
READ_TIMEOUT = 30
RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 15

class BaseShuntClient:
    def __init__(self, config):
        self.config = config
        dev = config.get('device', config)
        self.device_id = int(dev['device_id'])
        self.alias = dev['alias']
        self.mac = dev['mac_addr']
        self.adapter = dev.get('adapter', 'hci0')
        self.sections = []
        self.section_index = 0
        self.data = {}
        self.loop = asyncio.get_event_loop()
        self.read_timeout_task = None
        self.reconnect_attempts = 0
        self.manager = None
        self.device = None
        _LOGGER.info(f"Init {self.__class__.__name__}: {self.alias} => {self.mac}")

    def start(self):
        asyncio.ensure_future(self._run())

    async def _run(self):
        try:
            await self.connect()
            await self.manager.run()
        except Exception as e:
            await self.__on_error(True, e)

    async def connect(self):
        self.manager = DeviceManager(mac_address=self.mac, alias=self.alias, adapter=self.adapter)
        await self.manager.discover()

        if not self.manager.device_found:
            logging.error(f"Device not found: {self.alias} => {self.mac}")
            for dev in self.manager.devices():
                if dev.alias() and (dev.alias().startswith(ALIAS_PREFIX) or dev.alias().startswith(ALIAS_PREFIX_PRO)):
                    logging.debug(f"Possible device: {dev.alias()} [{dev.mac_address}]")
            return await self.__stop_service()

        self.device = Device(
            mac_address=self.mac,
            manager=self.manager,
            on_resolved=self.__on_resolved,
            on_data=self.on_data_received,
            on_connect_fail=self.__on_connect_fail,
            notify_uuid=NOTIFY_CHAR_UUID,
            write_uuid=WRITE_CHAR_UUID
        )

        while self.reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
            try:
                _LOGGER.info(f"Connecting (attempt {self.reconnect_attempts+1})...")
                await self.device.connect()
                self.reconnect_attempts = 0
                _LOGGER.info("Connected successfully")
                return
            except Exception as e:
                self.reconnect_attempts += 1
                logging.warning(f"Connect failed: {e}, retrying in {RECONNECT_DELAY}s")
                await asyncio.sleep(RECONNECT_DELAY)

        logging.error("Max reconnect attempts reached.")
        await self.__on_error(True, "Max reconnect attempts reached.")

    async def disconnect(self):
        if self.device:
            await self.device.disconnect()
        await self.__stop_service()

    def __on_resolved(self):
        _LOGGER.info("resolved services")
        asyncio.ensure_future(self.poll_data() if self.config.get('data', {}).get('enable_polling', False) else self.read_section())

    async def read_section(self):
        # Reset data at the start of a full read cycle (section_index == 0)
        if self.section_index == 0:
            self.data = {}
        if not self.sections or self.device_id is None:
            logging.error("No sections or device_id defined")
            return

        req = self.create_generic_read_request(self.device_id, 3, self.sections[self.section_index]['register'], self.sections[self.section_index]['words'])
        await self.device.characteristic_write_value(req)
        self.read_timeout_task = self.loop.call_later(READ_TIMEOUT, lambda: asyncio.ensure_future(self.on_read_timeout()))

    async def on_read_timeout(self):
        logging.error("on_read_timeout => please check your device_id!")
        await self.disconnect()

    def on_data_received(self, response):
        if self.read_timeout_task and not self.read_timeout_task.cancelled():
            self.read_timeout_task.cancel()

        operation = bytes_to_int(response, 1, 1)
        if operation == 87 and self.section_index < len(self.sections):
            parser = self.sections[self.section_index].get('parser')
            if parser:
                parsed_data = parser(response)
                if isinstance(parsed_data, dict):
                    self.data.update(parsed_data)
            if self.section_index >= len(self.sections) - 1:
                self.section_index = 0
                self.__safe_callback(self.on_data_callback, self.data)
                asyncio.ensure_future(self.poll_data())
            else:
                self.section_index += 1
                asyncio.ensure_future(self.read_section())
        else:
            logging.warning(f"Unknown operation={operation}")

    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = [device_id, function, int_to_bytes(regAddr, 0), int_to_bytes(regAddr, 1), int_to_bytes(readWrd, 0), int_to_bytes(readWrd, 1)]
        crc = crc16_modbus(bytes(data))
        data.extend([crc[0], crc[1]])
        logging.debug(f"create_request_payload {regAddr} => {data}")
        return data

    async def poll_data(self):
        await self.read_section()
        await asyncio.sleep(self.config['data'].getint('poll_interval', 60))
        await self.poll_data()

    async def __on_error(self, connectFailed=False, error=None):
        logging.error(f"Exception occurred: {error}")
        self.__safe_callback(self.on_error_callback, error)
        await (self.__stop_service() if connectFailed else self.disconnect())

    def __on_connect_fail(self, error):
        logging.error(f"Connection failed: {error}")
        asyncio.ensure_future(self.__on_error(True, error))

    def __safe_callback(self, callback, param):
        if callback:
            try:
                callback(self, param)
            except Exception as e:
                logging.error(f"Exception in callback: {e}")

    async def __stop_service(self):
        if self.manager:
            await self.manager.stop()
