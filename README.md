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

Connect a Samsung **MIM-B19N** Modbus board through a Modbus RTU-to-TCP gateway to expose heat pump readings and controls in Home Assistant. Communication stays on your local network.

This is a community integration, unaffiliated with Samsung or Home Assistant.

## Features

- **Monitor operation:** temperatures, pressures, compressor frequency, water flow, operating modes, error codes, and status bits.
- **Control the heat pump:** domestic hot water operation, DHW mode and setpoint, water-out setpoint, quiet mode, outing mode, and heating zone 1.
- **Write Field Setting Values (FSVs)** using a Home Assistant action and the included FSV-to-message-ID mapping.
- **Customize entities in YAML**, then reload the integration to apply changes without restarting Home Assistant.
- **Troubleshoot with context:** poll timing diagnostics, actionable service errors, and warnings for missing or unmapped register values.

Entities depend on the selected template and the capabilities of your heat pump and Modbus board.

## Hardware and connection

```text
Samsung EHS heat pump
        │
   MIM-B19N board
        │ Modbus RTU / RS-485
   RTU-to-TCP gateway
        │ Local network / Modbus TCP
   Home Assistant
```

You need a working MIM-B19N installation, a configured gateway (for example, a Waveshare RS485-to-Ethernet adapter), and its IP address, TCP port, and Modbus device ID. The gateway's serial settings must match the board.

The included [`samsung_mono_ehs_ht_quiet.yaml`](custom_components/samsung_modbus_hp/templates/samsung_mono_ehs_ht_quiet.yaml) describes:

| Unit | Model in the template |
| --- | --- |
| EHS Mono HT Quiet outdoor unit | AE080CXYDEK/EU, 8 kW |
| Tank Integrated Hydro Unit | AE200RNWMEG/EU, 200 l |

Other models may need a different template. Template presence does not guarantee that every firmware version exposes every message ID.

## Installation

### HACS

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/StackOverflowEx/Samsung-Modbus-Heatpump` as an **Integration** repository.
3. Download **Samsung Heatpump Modbus**.
4. Restart Home Assistant for the initial installation.
5. Go to **Settings → Devices & services → Add integration**, then search for **Samsung Heatpump Modbus**.

### Manual

Copy the `custom_components/samsung_modbus_hp` directory into your Home Assistant configuration directory:

```text
config/
└── custom_components/
    └── samsung_modbus_hp/
        ├── manifest.json
        ├── fsv_mapping.json
        ├── brand/
        ├── templates/
        └── …
```

Restart Home Assistant, then add the integration through **Devices & services**.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| Host | Required | Gateway hostname or IP address |
| Port | `502` | Modbus TCP port |
| Device ID | `1` | Modbus unit/slave ID behind the gateway |
| Scan interval | `30` seconds | Time between polls |
| Template filename | `samsung_mono_ehs_ht_quiet.yaml` | YAML path relative to `templates/` |

Use the integration's **Configure** option to change these settings. Saving options reloads the integration.

### Custom templates

For changes you want to keep across HACS updates, copy the included template into `templates/custom/`, for example `templates/custom/my_heatpump.yaml`, and set the template filename to `custom/my_heatpump.yaml`. HACS is configured to preserve this directory.

Each device defines its entities under `registers`. A register can use a fixed `address` or a Samsung `messageId`. Message IDs require the device's `bindMessageIdRegisterOffset` and `readMessageIdRegisterOffset`; addresses are assigned in template order.

For example, this register definition creates a temperature sensor:

```yaml
- name: Water In Temperature
  messageId: 0x82DF
  scale: 0.1
  signed: true
  unit_of_measurement: "°C"
  device_class: temperature
  state_class: measurement
```

Supported platforms are `sensor` (the default), `binary_sensor`, `switch`, `select`, and `number`. See the included template for mappings, bit definitions, setpoint limits, and write timeouts. Multi-register data is not supported.

For registers that can be negative, add `signed: true` to their YAML definition. This decodes a 16-bit two's-complement value before applying `scale`: for example, raw `65526` becomes `-10`, then `-1.0 °C` with `scale: 0.1`. The included template enables this for all temperature registers. Registers without `signed: true` remain unsigned (`0`–`65535`), preserving status bits, error codes, and counters.

Custom templates also need `signed: true` on their temperature definitions; reload after editing them. Signed number controls encode negative values back into the unsigned Modbus word, including optimistic readback. Their raw signed range is `-32768`–`32767`; the template's `min` and `max` still define the allowed setpoint range. The FSV action continues to accept raw unsigned words.

### Register masks

Use `masks` to expose multiple fields of one register. Each field can specify `platform: binary_sensor`, `switch`, or `number`. A platform on the parent remains the default for its fields, so existing binary-sensor templates keep working:

```yaml
- name: Communication Status
  address: 50
  platform: binary_sensor
  masks:
    - name: Address Exists
      mask: 1
    - name: Type OK
      mask: 2
    - name: Device Ready
      mask: 4
    - name: Communication Error
      mask: 8
```

This creates entities named **Communication Status Address Exists**, **Communication Status Type OK**, and so on (Home Assistant can also prefix the device name). A sensor is ON when **any** bit selected by its mask is set: `(raw_value & mask) != 0`. Decimal, hexadecimal, and binary YAML integers are supported, for example `2`, `0x02`, and `0b10`. Missing register data stays Unknown, including for inverted masks.

Use `invert: true` when the output is ON while the selected bit is clear. For the supplied `0x408A` two-way valve table, zone 1 (B10) uses **bit 0**, and zone 2 (B14) uses **bit 1**:

```yaml
- name: Pump Status
  messageId: 0x408A
  platform: binary_sensor
  masks:
    - name: Zone 1
      mask: 0b01
      invert: true
    - name: Zone 2
      mask: 0b10
      invert: true
```

| Raw value | Pump Status Zone 1 (B10) | Pump Status Zone 2 (B14) |
| --- | --- | --- |
| 0 | ON | ON |
| 1 | OFF | ON |
| 2 | ON | OFF |
| 3 | OFF | OFF |

Alternatively, use `mask` directly on a `binary_sensor`, `switch`, or `number` definition. Boolean fields also support `invert`. Multiple definitions may share a `messageId` or fixed `address`; give each entity a distinct name:

```yaml
- name: Zone 1 Valve
  messageId: 0x408A
  platform: binary_sensor
  mask: 1
  invert: true
- name: Zone 2 Valve
  messageId: 0x408A
  platform: binary_sensor
  mask: 2
  invert: true
```

Repeated message IDs share one binding and register address per device. Unique IDs are bound in order of first appearance. Masks cannot be combined with `mapping` on the same definition.

The included template exposes Modbus Module Error Status as three individual error sensors plus an `Any` summary binary sensor, and Communication Status as four binary sensors. Unsupported register options are rejected during template loading.

### Frequency Response Control

The included tank-integrated hydro unit template exposes message ID `0x42F1` as an enable switch and a frequency ratio number. The MIM-B19N manual (page 18) specifies **byte 1 / upper byte** for enable (`0` or `1`) and **byte 0 / lower byte** for the ratio (`50`–`150%`):

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
      step: 1
      unit_of_measurement: "%"
      mode: box
```

This creates **Frequency Response Control Enabled** and **Frequency Response Control Frequency Ratio**, sharing one custom-register slot. This function is documented for tank-integrated hydro units only.

Writable masks must select contiguous bits and use unsigned values. The integration automatically shifts the field into and out of its position before applying a number's `scale`. A switch writes `0` or `1` into its field. For example, enabled at 80% is `0x0150`; disabling writes `0x0050`, preserving the ratio.

Field writes run as a serialized read/modify/write operation. The integration reads the register before updating it, or uses a pending accepted write while waiting for delayed device readback. It preserves the other field, rejects invalid reads and out-of-range values, and updates both entities after an accepted write. Concurrent writes within this integration are serialized; changes made by an external controller between reading and writing cannot be made atomic by this mechanism.

### Custom register boundaries

The integration enforces the MIM-B19N address layout:

| Device | Binding start | Custom data addresses | Maximum unique message IDs |
| --- | --- | --- | --- |
| Outdoor | `6000` | `4`–`49` | **46** |
| Indoor unit 0 | `7000` | `82`–`99` | **18** |
| Indoor unit n (0–47) | `7000` | `82 + 50n` through `99 + 50n` | **18** |

An oversized template or incorrect binding/read offset fails setup with a contextual error. Fixed-address entries in a device with configured binding offsets must also stay inside that device's 50-address block. Repeated message IDs and multiple masked entities count as one slot.

The same check applies **before** a dynamic FSV binding is sent. If an FSV's message ID is not already bound, one free slot is required. A full binding list can still write an FSV whose message ID is already present. The generic Modbus limit of 123 registers per binding request does not override these smaller device limits.

### Reload after editing YAML

Go to **Settings → Devices & services**, open the integration entry's menu, and choose **Reload**. You can also run this in **Developer tools → Actions**:

```yaml
action: samsung_modbus_hp.reload
data: {}
```

This reloads all configured Samsung Modbus heat pumps, re-reads their templates, rebinds message IDs, and recreates their entities. Select a **Configuration entry** in the action editor to reload only one installation. Entities may briefly become unavailable while reloading.

Adding or editing a sensor in the selected YAML file only needs a reload. Renaming an entity or unit changes its unique ID and can leave an old entity registry entry to remove manually. Installing or updating Python code still needs a Home Assistant restart.

## Set a Field Setting Value

Run **Samsung Heatpump Modbus: Set Field Setting Value (FSV)** from **Developer tools → Actions**. Supply:

| Field | Meaning |
| --- | --- |
| `device_id` | Select the target unit from the device dropdown |
| `fsv_code` | FSV number, such as `2011`, listed in [`fsv_mapping.json`](custom_components/samsung_modbus_hp/fsv_mapping.json) |
| `value` | Raw unsigned 16-bit register value (`0`–`65535`) |

The device dropdown resolves the unit and configuration entry automatically, even when two installations use the same unit name or you rename a device in Home Assistant. A device selection is required. The FSV mapping is read for each call, so JSON edits take effect on the next call.

**Check the service documentation for your exact heat pump before changing an FSV.** Values are sent raw, without unit conversion or validation of the FSV's model-specific range. Use the encoding and allowed range specified for that setting.

An unknown FSV code, invalid value, missing unit, ambiguous target, failed binding, or rejected Modbus write raises a visible Home Assistant action error and is logged. A successful action means the Modbus write was accepted; it does not independently verify that the heat pump applied the setting.

## Set a heating or cooling curve

Run **Samsung Heatpump Modbus: Set Heating Curve**, select the device, then choose **Heating 1**, **Heating 2**, **Cooling 1**, or **Cooling 2**. Enter the lower and upper outdoor temperatures and the water outlet temperature at each outdoor endpoint in whole °C. Negative outdoor temperatures are encoded automatically.

**Outdoor endpoints are shared:** changing either Heating curve changes the outdoor endpoints of **both Heating curves**. Changing either Cooling curve similarly affects **both Cooling curves**. The selected curve's water endpoints are independent.

| Curve | Outdoor lower / upper FSV | Water FSV at lower / upper outdoor endpoint | Outdoor lower / upper range | Water range |
| --- | --- | --- | --- | --- |
| Heating 1 | 2011 / 2012 | 2021 / 2022 | −20–5°C / 10–20°C | 17–75°C* |
| Heating 2 | 2011 / 2012 | 2031 / 2032 | −20–5°C / 10–20°C | 17–75°C* |
| Cooling 1 | 2051 / 2052 | 2061 / 2062 | 25–35°C / 35–45°C | 5–25°C |
| Cooling 2 | 2051 / 2052 | 2071 / 2072 | 25–35°C / 35–45°C | 5–25°C |

*The heating maximum is **65, 70 or 75°C depending on the outdoor unit**. Values above 65°C require a compatible model; the action displays and logs a warning but cannot determine your model's limit. The manual also warns against **Cooling 1 below 16°C for underfloor cooling** because of condensation.

The lower outdoor temperature must be strictly below the upper one. **Heating curves must fall strictly:** `2021 > 2022` for Heating 1 and `2031 > 2032` for Heating 2. Equal or reversed heating water endpoints are rejected before any writes.

Cooling normally also falls (`2061 > 2062` or `2071 > 2072`). Equal or reversed cooling endpoints are allowed with a warning in Home Assistant's logs, without swapping the values. The input names identify the outdoor endpoints, so `water_temperature_at_lower_outdoor` always writes `2061/2071`, even when its value is numerically lower. Model support for reversed curves is not verified.

A rising cooling curve is not condensation protection: indoor air temperature and humidity determine the indoor dew point. Raising the water temperature when that dew point rises can help, but outdoor temperature alone is not sufficient. Dew-point control should keep chilled surfaces above the room dew point or stop cooling when necessary ([ASHRAE: Radiant Heating and Cooling](https://handbook.ashrae.org/Handbooks/A19/SI/a19_ch55/A19_Ch55_si.aspx)).

```yaml
action: samsung_modbus_hp.set_heating_curve
data:
  device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
  curve: heating_1
  outdoor_temperature_lower: -10
  outdoor_temperature_upper: 15
  water_temperature_at_upper_outdoor: 25
  water_temperature_at_lower_outdoor: 40
```

All four values, mapping entries and register capacity are checked before writing. The sequence reuses one temporary register slot and prevents other Modbus operations from interleaving. Hardware writes remain sequential: if one fails, the action stops and reports the number of accepted writes; earlier writes are not rolled back. Success confirms Modbus acceptance, not independent heat-pump readback. This action edits the curve without changing the active curve selection or heating/cooling mode.

### Use actions in automations and scripts

All integration actions are available in automation and script editors through **Add action → Perform action**. Select **Set Heating Curve**, **Set Field Setting Value (FSV)**, or **Reload configuration** and fill in the same fields used in Developer tools. For example, the actions section of an automation can contain:

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

Use the device picker to populate the device ID. The same validation and warnings apply when called from automations or scripts.

## Troubleshooting

### Why is a sensor “Unknown”?

A sensor is **Unknown** when its value is `None` while the integration remains available. This happens when:

- Its register has no value in the coordinator's data.
- A mapping has no entry for the raw value and no `fallback`.
- A binary sensor's mapped value cannot be interpreted as `On`, `Off`, or a boolean.

For example, **Operation Status** maps values `0`–`4`. A raw value of `5` is unknown unless the template adds a mapping or fallback. Warnings identify the unit, entity, register address, and message ID; unmapped values include the raw value. Repeated reads of the same problem do not flood the log.

A text fallback such as `fallback: "Unknown {value}"` produces a literal state such as `Unknown 5`; that is different from Home Assistant's special `unknown` state. Sensors with dynamic fallbacks are text sensors rather than fixed-choice enums. Select entities only accept their declared options.

Missing bit-register data is also unknown; it must not be mistaken for `OK` or `Off`.

### Why is a sensor “Unavailable”?

A failed poll—such as a connection error, Modbus exception, or incomplete register response—marks the coordinator unavailable. All entities sharing that configuration entry become **Unavailable** until polling succeeds again. The coordinator logs failures and recovery.

Check the gateway address, port, device ID, serial configuration, and template addresses. Invalid templates fail setup with a contextual error instead of silently skipping bindings.

### A setpoint changes back after writing

Controls temporarily display an accepted write while waiting for the device to report it. The default timeout is one scan interval; a register can override it with `timeout` in seconds. If readback still differs after the timeout, the integration displays the device's actual value and logs **Write not confirmed**, including requested and observed values.

### Enable debug logs

Use **Enable debug logging** on the integration in Home Assistant, or add:

```yaml
logger:
  default: warning
  logs:
    custom_components.samsung_modbus_hp: debug
```

Include the relevant log lines, Home Assistant version, heat pump model, gateway model, and template changes when [reporting an issue](https://github.com/StackOverflowEx/Samsung-Modbus-Heatpump/issues).

## Integration icon

Home Assistant **2026.3 and newer** can load the bundled Samsung images from `custom_components/samsung_modbus_hp/brand/`. No separate brands-repository submission or manifest icon URL is needed. Earlier Home Assistant versions may show a generic integration icon.

Images are sourced from the [Home Assistant brands repository](https://github.com/home-assistant/brands/tree/master/core_brands/samsung). See [Home Assistant's brand image documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/) for details. Samsung's name and logo belong to their respective owner.

## Development

Tests exercise real Home Assistant entity and service classes with mocked Modbus responses; they do not contact a heat pump. In an environment containing Home Assistant, the manifest dependencies, `pytest`, and `pytest-asyncio`, run:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -p pytest_asyncio.plugin -q tests
```

Coverage includes device-picker targeting and action schemas, heating/cooling FSV mappings, temperature limits and curve slope checks, signed curve encoding, shared-endpoint warnings, concurrent and partially failed FSV sequences, register boundaries, masked entities and writes, and template parsing. Modbus responses are mocked; tests do not operate a physical heat pump.
