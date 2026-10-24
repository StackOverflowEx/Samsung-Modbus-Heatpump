<p align="center">
  <img src="custom_components/samsung_modbus_hp/brand/icon@2x.png" alt="Samsung" width="128">
</p>

<h1 align="center">Samsung Modbus Heat Pump</h1>
<p align="center">Local monitoring and control of Samsung EHS heat pumps in Home Assistant.</p>

<p align="center">
  <a href="https://github.com/StackOverflowEx/Samsung-Modbus-Heatpump/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/StackOverflowEx/Samsung-Modbus-Heatpump"></a>
  <a href="https://www.home-assistant.io/"><img alt="Home Assistant custom integration" src="https://img.shields.io/badge/Home_Assistant-custom_integration-18BCF2"></a>
  <img alt="Local polling" src="https://img.shields.io/badge/connection-local_polling-168C70">
</p>

Connect a Samsung **MIM-B19N** board through a **Modbus RTU-to-TCP gateway** for local monitoring, controls, and Field Setting Value (FSV) actions. Entities are configured in YAML and depend on your heat pump's capabilities.

Community integration; not affiliated with Samsung or Home Assistant.

## Installation

1. In **HACS → Custom repositories**, add `https://github.com/StackOverflowEx/Samsung-Modbus-Heatpump` as an **Integration**.
2. Install **Samsung Heatpump Modbus** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration** and search for **Samsung Heatpump Modbus**.

For manual installation, copy `custom_components/samsung_modbus_hp` into your Home Assistant configuration directory, restart, and add the integration.

The gateway's serial settings must match the MIM-B19N board. The [included template](custom_components/samsung_modbus_hp/templates/samsung_mono_ehs_ht_quiet.yaml) targets the AE080CXYDEK/EU outdoor unit and AE200RNWMEG/EU tank-integrated hydro unit; adapt it for other models.

## Configuration

✅ Required. Other entries show their default or `—` when unset.

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| ✅ Host | string | — | Gateway hostname or IP address. |
| Port | integer | `502` | Modbus TCP port. |
| Device ID | integer | `1` | Modbus unit/slave ID. |
| Scan interval | integer | `30` | Poll interval in seconds. |
| Template filename | string | `samsung_mono_ehs_ht_quiet.yaml` | Path relative to `templates/`. |

Change settings through **Configure**. For custom templates, copy the supplied YAML to `templates/custom/my_heatpump.yaml` and select `custom/my_heatpump.yaml`; HACS preserves this directory.

### Template and device keys

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | `Unknown Device` | Top-level template name. |
| ✅ `devices` | list | — | Device definitions below; at least one required. |
| `devices[].name` | string | `Unknown SubDevice` | Unique device name within the template. |
| `model` | string | `Unknown Model` | Device model. |
| `capacity` | number/string | `Unknown Capacity` | Capacity shown by the diagnostic sensor. |
| `capacity_unit` | string | — | Capacity unit, e.g. `kW` or `l`. |
| `bindMessageIdRegisterOffset` | integer | — | Binding register; required for `messageId` entries. |
| `readMessageIdRegisterOffset` | integer | — | First custom data register; required for `messageId` entries. |
| `registers` | list | `[]` | Entity definitions using the keys below. |

Except for the top-level `name` and `devices`, these keys belong inside each device definition.

### Register keys

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| ✅ `name` | string | — | Entity name; use distinct names within a device. |
| `address` | integer | — | Fixed Modbus address; supply this or `messageId`. |
| `messageId` | integer | — | Samsung message ID, e.g. `0x82DF`; assigned a custom slot. |
| `platform` | string | `sensor` | `sensor`, `binary_sensor`, `switch`, `select`, or `number`. |
| `signed` | boolean | `false` | Decode signed 16-bit values before scaling; enable for negative temperatures. |
| `scale` | number | `1` | Multiplier for sensor/number values, e.g. `0.1`. |
| `unit_of_measurement` | string | — | Sensor/number unit, e.g. `°C`. |
| `device_class` | string | — | Sensor/number device class, e.g. `temperature`. |
| `state_class` | string | — | Sensor/number state class, e.g. `measurement`. |
| `mapping` | object | — | Raw values to sensor/select/binary-sensor states; optional `fallback`. |
| `min` / `max` | number | `0` / `100` | Number entity limits after scaling. |
| `step` | number | `1` | Number entity increment. |
| `mode` | string | `box` | Number input: `box`, `slider`, or `auto`. |
| `timeout` | number | Scan interval | Seconds to display an accepted write while awaiting readback. |
| `mask` | integer | — | Bit mask for a binary sensor, switch, or number. |
| `invert` | boolean | `false` | Reverse a masked binary sensor or switch. |
| `masks` | list | — | Multiple named fields sharing this register; see below. |

Repeated message IDs share one slot. Only single 16-bit registers are supported. Unsupported keys are rejected.

```yaml
- name: Water In Temperature
  messageId: 0x82DF
  signed: true
  scale: 0.1
  unit_of_measurement: °C
  device_class: temperature
  state_class: measurement
```

### Mask fields

Each `masks` entry requires `name` and `mask`. It inherits parent settings and may override `platform`, `invert`, `min`, `max`, `step`, `scale`, `unit_of_measurement`, `device_class`, `mode`, and `timeout`. Entity names combine the parent and field names.

Binary sensors turn on when **any masked bit is set**; `invert: true` reverses this. Writable masks must be contiguous and unsigned. Masks cannot be combined with `mapping`.

For example, Frequency Response Control uses one register for a switch and a percentage control (tank-integrated hydro units):

```yaml
- name: Frequency Response Control
  messageId: 0x42F1
  masks:
    - name: Enabled
      platform: switch
      mask: 0xFF00
    - name: Frequency Ratio
      platform: number
      mask: 0x00FF
      min: 50
      max: 150
      unit_of_measurement: "%"
```

### Register limits

| Device | Binding start | Custom data addresses | Maximum slots | Maximum with FSV actions |
| --- | --- | --- | --- | --- |
| Outdoor | `6000` | `4–49` | 46 | **45** |
| Indoor unit n (`0–47`) | `7000` | `82 + 50n` to `99 + 50n` | 18 | **17** |

Boundaries are validated during setup. Each unique message ID uses one slot, regardless of its entity or mask count. **FSV actions require one free slot**: a full configuration logs a warning and rejects FSV actions, while normal entities remain available. Multi-value actions reuse that slot sequentially.

## Actions

Available in **Developer tools → Actions**, automations, and scripts (**Add action → Perform action**).

### Set Field Setting Value — `samsung_modbus_hp.set_field_setting_value`

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `device_id` | device | ✅ | Select the target unit from the dropdown. |
| `fsv_code` | string/integer | ✅ | Code from [fsv_mapping.json](custom_components/samsung_modbus_hp/fsv_mapping.json), e.g. `2011`. |
| `value` | integer | ✅ | Raw unsigned register value, `0–65535`. |

Values are sent without scaling or model-specific range checks. Check your heat pump's manual before writing.

### Set Heating Curve — `samsung_modbus_hp.set_heating_curve`

All temperatures are whole °C; negative values are encoded automatically.

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `device_id` | device | ✅ | Target unit. |
| `curve` | select | ✅ | `heating_1`, `heating_2`, `cooling_1`, or `cooling_2`. |
| `outdoor_temperature_lower` | integer | ✅ | Heating: `−20–5`; cooling: `25–35`. |
| `outdoor_temperature_upper` | integer | ✅ | Heating: `10–20`; cooling: `35–45`; must exceed the lower endpoint. |
| `water_temperature_at_lower_outdoor` | integer | ✅ | Water temperature at the lower outdoor endpoint. Heating: `17–75`; cooling: `5–25`. |
| `water_temperature_at_upper_outdoor` | integer | ✅ | Water temperature at the upper outdoor endpoint. Same ranges as above. |

- **Outdoor endpoints affect both curves of the selected mode.** Water endpoints affect only the selected curve; the action does not change the active curve or operating mode.
- Heating must slope down: `2021 > 2022` / `2031 > 2032`. Flat or rising cooling curves are allowed with a log warning; hardware support is not verified.
- Heating above **65°C** requires a compatible outdoor unit. For underfloor cooling, the manual warns against Cooling 1 below **16°C**; a curve alone does not provide dew-point protection.
- Writes are sequential. On failure, earlier accepted writes are not rolled back. Success means Modbus acceptance, not verified heat-pump readback.

Example automation action:

```yaml
actions:
  - action: samsung_modbus_hp.set_heating_curve
    data:
      device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
      curve: heating_1
      outdoor_temperature_lower: -10
      outdoor_temperature_upper: 15
      water_temperature_at_lower_outdoor: 40
      water_temperature_at_upper_outdoor: 25
```

### Reload — `samsung_modbus_hp.reload`

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `entry_id` | configuration entry | All entries | Optionally select one installation to reload. |

After YAML changes, run this action or choose **Reload** in the integration menu. Python code updates require a restart. Renaming template devices/entities changes their unique IDs.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| **Unknown** | Missing register data or a value without a matching mapping/fallback; see the logged warning. |
| **Unavailable** | Failed polling: check gateway, port, device ID, serial settings, and register addresses. |
| Setpoint changes back | Device readback differs after `timeout`; look for **Write not confirmed**. |
| FSV action unavailable | Leave at least one custom register slot free. |

Use **Enable debug logging** on the integration. When [reporting an issue](https://github.com/StackOverflowEx/Samsung-Modbus-Heatpump/issues), include relevant logs, Home Assistant version, hardware models, and template changes.

Samsung brand images come from the [Home Assistant brands repository](https://github.com/home-assistant/brands/tree/master/core_brands/samsung); see [brand credits](custom_components/samsung_modbus_hp/brand/README.md).
