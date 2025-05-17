from homeassistant import config_entries
import voluptuous as vol
import asyncio
import logging
import os

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Try to import bleak only when scanning
try:
    from bleak import BleakScanner
except ImportError:
    BleakScanner = None

class RenogyBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        schema = vol.Schema({
            vol.Optional("scan_for_devices", default=True): bool
        })

        if user_input is not None:
            if user_input.get("scan_for_devices"):
                return await self.async_step_scan()
            else:
                return await self.async_step_manual()

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_scan(self, user_input=None):
        if BleakScanner is None:
            _LOGGER.warning("bleak not available, falling back to manual entry")
            return await self.async_step_manual()

        try:
            self.devices = await self._async_scan_ble()
        except Exception as e:
            _LOGGER.warning("BLE scan failed: %s", e)
            return await self.async_step_manual()

        if not self.devices:
            _LOGGER.info("No BLE devices found, falling back to manual entry")
            return await self.async_step_manual()

        device_options = {
            d.address: f"{d.name or 'Unknown'} ({d.address})"
            for d in self.devices
        }

        self.device_index = {d.address: d for d in self.devices}

        schema = vol.Schema({
            vol.Required("mac"): vol.In(device_options)
        })

        return self.async_show_form(
            step_id="select_device",
            data_schema=schema,
        )

    async def async_step_select_device(self, user_input=None):
        selected_mac = user_input["mac"]
        device = self.device_index[selected_mac]

        alias = device.name or "Renogy Shunt"
        adapter = await self._get_default_adapter()
        device_id = "255"

        schema = vol.Schema({
            vol.Required("alias", default=alias): str,
            vol.Required("mac", default=selected_mac): str,
            vol.Required("adapter", default=adapter): str,
            vol.Required("device_id", default=device_id): str,
        })

        return self.async_show_form(
            step_id="confirm_entry",
            data_schema=schema,
        )

    async def async_step_manual(self, user_input=None):
        adapter = await self._get_default_adapter()
        schema = vol.Schema({
            vol.Required("alias", default="Renogy Shunt"): str,
            vol.Required("mac"): str,
            vol.Required("adapter", default=adapter): str,
            vol.Required("device_id", default="255"): str,
        })

        return self.async_show_form(
            step_id="confirm_entry",
            data_schema=schema,
        )

    async def async_step_confirm_entry(self, user_input=None):
        await self.async_set_unique_id(user_input["mac"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=user_input["alias"], data=user_input)

    async def async_step_import(self, import_config):
        """Import existing YAML config into config entries."""
        return await self.async_step_user(import_config)

    async def _async_scan_ble(self):
        return await BleakScanner.discover()

    async def _get_default_adapter(self):
        # Run blocking os.listdir in executor
        adapters = await self.hass.async_add_executor_job(
            lambda: [f for f in os.listdir("/sys/class/bluetooth/") if f.startswith("hci")]
        )
        return adapters[0] if adapters else "hci0"
