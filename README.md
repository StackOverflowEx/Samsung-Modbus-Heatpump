# Samsung Modbus Heat Pump integration for Home Assistant

When the Samsung MIM-B19N extension board is connected to the heat pump and the Modbus RTU is converted to
Modbus TCP (e.g. using a Waveshare RS486 to ETH (B) adapter) you can use this custom integration to read various sensors and control the heat pump from Home Assistant.

## Templates
The integration supports loading register definitions from YAML templates, which can be customized and shared. A template for the Samsung Mono EHS HT Quiet is included in the repository, and you can create your own by following the structure of that file.
