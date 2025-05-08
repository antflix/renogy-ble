# renogy_ble

This [renogy_ble](https://github.com/realrube/renogy_ble/edit/main) project is a custom component for Home Assistant allowing sensors to be collected via Bluetooth BLE using the Renogy BT-2 interface connected to Renogy Rover (in my case RBC50D1S) and similar products.  It was developed and tested on a Raspberry Pi 4B 4GB running the Home Assistant OS (6.6.62-haos-raspi).

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

## Borrowed code

This project borrowed some code from the [cyrils/renogy-bt](https://github.com/cyrils/renogy-bt) project by a different author.  Only certain functionality is borrowed, namely the RoverClient and its dependencies which were then modified to work with Home Assistant.  It's not the most elegant, but works and is a good starting point.

    BaseClient.py  (modified)
    BLEManager.py  (modified)
    RoverClient.py (modified)
    Utils.py       (original)

## New code in this project

    __init__.py
    sensor.py

## Instructions:

Place all code into a new directory "renogy_ble" within Home Assistant's structure:  

    /root/homeassistant/custom_components/renogy_ble
    
It's recommended to install Advanced SSH & Web Terminal and File editor Add-Ons in order to manipulate the code.

Edit \_\_init__.py to suit your Renogy/Rover charger (search for MODIFY - Bluetooth MAC address and ID are required, you can find this by using the command "bluetoothctl devices").  This was quick and dirty method to avoid the configuration file from the original renogy-by project and minimize code for a quick proof of concept.  Maybe will clean up one day and use HA's built-in configuration mechanisms.

There are dependences that Python requires, and since using the Home Assistant OS, updates have to be made inside the Home Assistant container to persist after a reboot.  This worked for me:

    docker exec -it $(docker ps -f name=homeassistant -q) /bin/sh
    pip install bleak configparser requests
    exit

Edit Home Assistant's configuration file configuration.yaml to recognize the custom component, add:

    renogy_ble:

For added logging, also add:

    logger:
      default: info
      logs:
        custom_components.renogy_ble: debug

Restart Home Assistant and take a look at Settings->System->Logs->...->Show Raw Logs

You should see various info pass by after the BLE device is detected and a connection is made:

    2025-03-16 12:31:10.657 INFO (MainThread) [root] on_read_operation_complete
    2025-03-16 12:31:10.657 INFO (MainThread) [custom_components.renogy_ble] BT-TH-4817EE26 => {'function': 'READ', 'model': 'RBC50D1S-G4', 'device_id': 96, 'battery_percentage': 100, 'battery_voltage': 14.4, 'battery_current': 0.0, 'battery_temperature': 13, 'controller_temperature': 15, 'load_status': 'off', 'load_voltage': 0.0, 'load_current': 0.0, 'load_power': 0, 'pv_voltage': 0.0, 'pv_current': 0.0, 'pv_power': 0, 'max_charging_power_today': 682, 'max_discharging_power_today': 682, 'charging_amp_hours_today': 6, 'discharging_amp_hours_today': 0, 'power_generation_today': 82, 'power_consumption_today': 0, 'power_generation_total': 95, 'charging_status': 'deactivated', 'battery_type': None, '__device': 'BT-TH-4817EE26', '__client': 'RoverClient'}
    2025-03-16 12:31:10.657 INFO (MainThread) [custom_components.renogy_ble] Updated sensor: BT-TH-4817EE26 Battery Percentage with state: 100
    etc...

I found that a device ID of 255 worked, but sometimes an ID of 97 worked also.  This is a modbus thing, 255 is a broadcast ID so likely will only work if you have one client on your bus.

You can now add the sensors to your dashboard.

Remove the extra logging from configuration.yaml if everything is working fine.

## Enjoy!

## Disclaimer
This is not an official library endorsed by the device manufacturer. Renogy and all other trademarks in this repo are the property of their respective owners and their use herein does not imply any sponsorship or endorsement.
