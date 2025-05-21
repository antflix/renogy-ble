

import time
import os
import logging
import configparser
import asyncio
from .Utils import bytes_to_int, int_to_bytes, crc16_modbus
from .BLE import DeviceManager, Device
from bleak import BleakClient
from .BaseClient import BaseClient


_LOGGER = logging.getLogger(__name__)
ALIAS_PREFIX = 'RMTShunt300'
ALIAS_PREFIX_PRO = 'Shunt300'
NOTIFY_CHAR_UUID = "0000c411-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID  = ""
READ_TIMEOUT = 30
RECONNECT_DELAY = 5
MAX_RECONNECT_ATTEMPTS = 15
class BaseShuntClient(BaseClient):
    def __init__(self, config):
        self.config = config
        dev = config.get('device', config)
        self.device_id = int(dev['device_id'])
        self.alias = dev['alias']
        self.mac = dev.get('mac_addr', dev.get('mac'))
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
        self._last_log_time = 0

    async def run(self):
        """Notification-only mode: connect once and then wait for notifications indefinitely."""
        await self.connect()
        # Keep the task alive so notifications continue to be processed
        while True:
            await asyncio.sleep(60)

    def start(self):
        """Begin notification-only client."""
        asyncio.ensure_future(self.run())

    async def connect(self):
        self.manager = DeviceManager(mac_address=self.mac, alias=self.alias, adapter=self.adapter)
        await self.manager.discover()

        if not self.manager.device_found:
            _LOGGER.error(f"Device not found: {self.alias} => {self.mac}")
            return await self.__stop_service()

        self.device = Device(
            mac_address=self.mac,
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
        _LOGGER.info("Services resolved; listening for notifications")
        # No manual read or polling required; rely on BLE notifications

    # Manual read_section logic is not needed with notification-only mode.
    # async def read_section(self):
    #     pass

    # async def on_read_timeout(self):
    #     pass

    def on_data_received(self, response):
        if self.read_timeout_task and not self.read_timeout_task.cancelled():
            self.read_timeout_task.cancel()

        response = self._realign_packet(response)
        if not response:
            _LOGGER.warning("Could not realign packet; skipping.")
            return

        operation = bytes_to_int(response, 1, 1)
        if operation == 87:
            for section in self.sections:
                parser = section.get('parser')
                if parser:
                    parsed = parser(response)
                    if isinstance(parsed, dict):
                        self.data.update(parsed)
            current_time = time.time()
            if current_time - self._last_log_time >= 10:
                self._last_log_time = current_time
                self.__safe_callback(self.on_data_callback, self.data)
        else:
            _LOGGER.warning(f"Unknown operation={operation}")

    def _realign_packet(self, buffer):
        MIN_LENGTH = 73
        HEADER_BYTE = 0x57
        for i in range(len(buffer) - MIN_LENGTH + 1):
            if buffer[i+1] == HEADER_BYTE:
                candidate = buffer[i:i+MIN_LENGTH]
                if len(candidate) >= MIN_LENGTH:
                    payload = candidate[:-2]
                    received_crc = candidate[-2:]
                    calculated_crc = crc16_modbus(payload)
                    if received_crc == bytes(calculated_crc):
                        return candidate
                    else:
                        _LOGGER.warning("CRC check failed for candidate at offset %d", i)
        return None

    def create_generic_read_request(self, device_id, function, regAddr, readWrd):
        data = [device_id, function, int_to_bytes(regAddr, 0), int_to_bytes(regAddr, 1), int_to_bytes(readWrd, 0), int_to_bytes(readWrd, 1)]
        crc = crc16_modbus(bytes(data))
        data.extend([crc[0], crc[1]])
        _LOGGER.debug(f"create_request_payload {regAddr} => {data}")
        return data

    # Polling is not needed in notification-only mode.
    # async def poll_data(self):
    #     pass

    async def __on_error(self, connectFailed=False, error=None):
        _LOGGER.error(f"Exception occurred: {error}")
        self.__safe_callback(self.on_error_callback, error)
        await (self.__stop_service() if connectFailed else self.disconnect())

    def __on_connect_fail(self, error):
        _LOGGER.error(f"Connection failed: {error}")
        asyncio.ensure_future(self.__on_error(True, error))

    def __safe_callback(self, callback, param):
        if callback:
            try:
                callback(self, param)
            except Exception as e:
                _LOGGER.error(f"Exception in callback: {e}")

    async def __stop_service(self):
        # Clean up resources: disconnect device if connected
        if self.device:
            await self.device.disconnect()
