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
  unit_of_measurement: "°C"
  device_class: temperature
  state_class: measurement
```

Supported platforms are `sensor` (the default), `binary_sensor`, `switch`, `select`, and `number`. See the included template for mappings, bit definitions, setpoint limits, and write timeouts. Register values are currently interpreted as unsigned 16-bit values; signed temperatures and multi-register data need explicit support before adding such definitions.

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
| `unit_name` | Device name from the template, such as `Tank Integrated Hydro Unit` |
| `fsv_code` | FSV number, such as `2011`, listed in [`fsv_mapping.json`](custom_components/samsung_modbus_hp/fsv_mapping.json) |
| `value` | Raw unsigned 16-bit register value (`0`–`65535`) |
| `entry_id` | Optional configuration entry; required when the unit name matches multiple installations |

The action editor lets you select the configuration entry. Unit name matching ignores case. The FSV mapping is read for each call, so JSON edits take effect on the next call.

**Check the service documentation for your exact heat pump before changing an FSV.** Values are sent raw, without unit conversion or validation of the FSV's model-specific range. Use the encoding and allowed range specified for that setting.

An unknown FSV code, invalid value, missing unit, ambiguous target, failed binding, or rejected Modbus write raises a visible Home Assistant action error and is logged. A successful action means the Modbus write was accepted; it does not independently verify that the heat pump applied the setting.

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

Coverage includes service errors, device addressing, concurrent FSV writes, invalid/incomplete responses, optimistic write confirmation, sensor mappings, template parsing, and reload actions.
