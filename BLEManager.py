
# This file is part of renogy_ble.

# renogy_ble is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# renogy_ble is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a co  

import asyncio
import logging
import sys
from bleak import BleakClient, BleakScanner, BLEDevice

DISCOVERY_TIMEOUT = 10  # max wait time to complete Bluetooth scanning (seconds)
MAX_RETRIES = 100  # Number of times to retry connection
RETRY_DELAY = 10 # Seconds to wait before retrying

class BLEManager:
    def __init__(self, mac_address, alias, on_data, on_connect_fail, notify_uuid, write_uuid):
        self.mac_address = mac_address.upper()
        self.device_alias = alias
        self.data_callback = on_data
        self.connect_fail_callback = on_connect_fail
        self.notify_char_uuid = notify_uuid
        self.write_char_uuid = write_uuid
        self.device: BLEDevice = None
        self.client: BleakClient = None
        self.discovered_devices = []
        self.is_connecting = False  # Prevent multiple simultaneous connection attempts

    async def discover(self):
        logging.info("Starting discovery...")
        self.discovered_devices = await BleakScanner.discover(timeout=DISCOVERY_TIMEOUT)
        logging.info("Devices found: %s", len(self.discovered_devices))

        for dev in self.discovered_devices:
            if dev.address and (dev.address.upper() == self.mac_address or (dev.name and dev.name.strip() == self.device_alias)):
                logging.info(f"Found matching device {dev.name} => {dev.address}")
                self.device = dev
                return  # Stop after finding the first match

    async def connect(self):
        if self.is_connecting:
            logging.warning("Already attempting connection. Skipping duplicate call.")
            return
        self.is_connecting = True

        if not self.device:
            logging.error("No device found! Cannot connect.")
            self.is_connecting = False
            return

        self.client = BleakClient(self.device)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logging.info(f"Attempt {attempt}/{MAX_RETRIES}: Connecting to device {self.device.address}...")
                await self.client.connect()
                if self.client.is_connected:
                    logging.info("Connected successfully!")
                    self.is_connecting = False
                    await self.setup_characteristics()
                    return  # Exit loop if connection is successful
            except Exception as e:
                logging.error(f"Connection attempt {attempt} failed: {e}")

            if attempt < MAX_RETRIES:
                logging.info(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)

        logging.error("Max retries reached. Connection failed.")
        self.connect_fail_callback(sys.exc_info())
        self.is_connecting = False

    async def setup_characteristics(self):
        try:
            for service in self.client.services:
                for characteristic in service.characteristics:
                    if characteristic.uuid == self.notify_char_uuid:
                        await self.client.start_notify(characteristic, self.notification_callback)
                        logging.info(f"Subscribed to notification {characteristic.uuid}")
                    if characteristic.uuid == self.write_char_uuid:
                        logging.info(f"Found write characteristic {characteristic.uuid}")
        except Exception as e:
            logging.error(f"Error setting up characteristics: {e}")

    async def notification_callback(self, characteristic, data: bytearray):
        logging.info("Notification received from device")
        await self.data_callback(data)

    async def characteristic_write_value(self, data):
        try:
            logging.info(f'Writing to {self.write_char_uuid}: {data}')
            await self.client.write_gatt_char(self.write_char_uuid, bytearray(data))
            logging.info('Write successful')
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f'Write failed: {e}')

    async def disconnect(self):
        if self.client and self.client.is_connected:
            logging.info(f"Disconnecting device: {self.device.name} {self.device.address}")
            await self.client.disconnect()
        else:
            logging.info("No active connection to disconnect.")

