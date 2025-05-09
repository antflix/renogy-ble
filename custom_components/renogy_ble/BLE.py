
import asyncio
import logging
from bleak import BleakClient, BleakScanner
_LOGGER = logging.getLogger(__name__)
class DeviceManager:
    def __init__(self, mac_address, alias=None, adapter='hci0'):
        self.mac_address = mac_address.upper()
        self.device_alias = alias
        self.adapter = adapter
        self.device_found = False
        self.device_info = None

    async def discover(self, timeout=5):
        devices = await BleakScanner.discover(timeout=timeout, adapter=self.adapter)
        for dev in devices:
            if dev.address.upper() == self.mac_address or (self.device_alias and dev.name == self.device_alias):
                _LOGGER.info("Found device: %s [%s]", dev.name, dev.address)
                self.device_found = True
                self.device_info = dev
                break
        if not self.device_found:
            logging.error("Device not found: %s", self.mac_address)

class Device:
    def __init__(self, mac_address, on_resolved, on_data, on_connect_fail, notify_uuid, write_uuid):
        self.mac_address = mac_address
        self.on_data = on_data
        self.on_resolved = on_resolved
        self.on_connect_fail = on_connect_fail
        self.notify_uuid = notify_uuid
        self.write_uuid = write_uuid
        self.client = BleakClient(mac_address)
        self.writing = None

    async def connect(self):
        try:
            await self.client.connect()
            _LOGGER.info("[%s] Connected", self.mac_address)
            await self.client.start_notify(self.notify_uuid, self._handle_notification)
            _LOGGER.info("[%s] Subscribed to notification %s", self.mac_address, self.notify_uuid)
            self.on_resolved()
        except Exception as e:
            logging.error("Connection failed: %s", e)
            self.on_connect_fail(e)

    async def disconnect(self):
        if self.client.is_connected:
            await self.client.disconnect()
            _LOGGER.info("[%s] Disconnected", self.mac_address)

    def _handle_notification(self, sender, data):
        self.on_data(bytearray(data))

    async def characteristic_write_value(self, value):
        if not self.write_uuid:
            logging.warning("Attempted write but write_uuid is empty.")
            return
        try:
            await self.client.write_gatt_char(self.write_uuid, bytearray(value), response=True)
            _LOGGER.info("Write successful: %s", self.write_uuid)
        except Exception as e:
            logging.error("Write failed: %s", e)
