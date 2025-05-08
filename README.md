
## Modified and new code in this fork

This fork was originally based on support for the Renogy Rover, but it has since been significantly reworked to support the **Renogy Smart Shunt** via Bluetooth using the Renogy BT-2 interface. The code is **not currently compatible with the Renogy Rover**, as the client logic and data extraction have been fully tailored to the Smart Shunt.

### Key Changes from the Original (`realrube/renogy_ble`)
- Full replacement of `RoverClient` logic with `ShuntClient`, designed specifically for interpreting Smart Shunt BLE data.
- Added `BaseShuntClient.py` and restructured the protocol handling for Shunt BLE characteristics.
- `BLEManager.py` and `BLE.py` updated to reflect the communication characteristics of the Renogy Smart Shunt.
- All files renamed to follow snake_case naming conventions for HACS compatibility.
- Created `hacs.json` for HACS discovery and updated `manifest.json` metadata.
- Sensor logic (`sensor.py`) simplified and adjusted to reflect only relevant Smart Shunt metrics.
- `__init__.py` updated with hardcoded BLE MAC and Device ID (which should be modified by the user—see below).

---


## Configuring for Your Renogy Smart Shunt

To use this integration with your own Smart Shunt, add the following to your `configuration.yaml` in Home Assistant:

```yaml
renogy_ble:
  devices:
    - alias: "MyShunt"
      mac_addr: "12:34:56:78:9A:BC"
      device_id: 255
      adapter: "hci0"
```

### Required Fields
- **alias**: This must match the BLE-advertised name of your Smart Shunt (e.g., `RMTShunt300XXXX`). You can discover this name by running `bluetoothctl` and looking for the alias listed next to your device’s MAC address. It is required for device discovery and matching.
- **mac_addr**: The MAC address of your Renogy Smart Shunt.
- **device_id**: The Modbus address of the device. Most users should use `255`, which is a broadcast ID. If you have multiple devices, try `97` or a specific ID.
- **adapter**: The name of your Bluetooth adapter (usually `hci0` on Raspberry Pi and Linux systems).


### Notes
- Configuration is now **fully handled in `configuration.yaml`**. No values are hardcoded in the source code.
- Missing fields will cause Home Assistant to log an error and skip setup for that device.
- You can run `bluetoothctl devices` on your system to find the alias and MAC address broadcasted by your Smart Shunt.

#### Example Log Output

When properly configured and connected, you should see log entries similar to:

```
[custom_components.renogy_ble] Initialized sensor MyShunt Charge Battery Voltage
[custom_components.renogy_ble] Found matching device RMTShunt300123456 => [12:34:56:78:9A:BC]
[custom_components.renogy_ble] Connected successfully!
[custom_components.renogy_ble] MyShunt => {'charge_battery_voltage': 13.12, 'discharge_amps': -4.25, 'state_of_charge': 87.5}
[custom_components.renogy_ble] Updated sensor: MyShunt Charge Battery Voltage with state: 13.12
```

These logs confirm successful BLE discovery, connection, data parsing, and Home Assistant sensor updates.
