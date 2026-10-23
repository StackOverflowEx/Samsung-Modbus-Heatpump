import aiofiles
import yaml
import logging
import math
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)


class DeviceTemplate:
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def load(self):
        self.definition = await self.read_yaml()
        if (
            not isinstance(self.definition, dict)
            or not isinstance(self.definition.get("devices"), list)
            or not self.definition["devices"]
        ):
            raise ValueError("Template must contain a non-empty devices list")
        if not all(isinstance(device, dict) for device in self.definition["devices"]):
            raise ValueError("Each device definition must be an object")
        self.device_name = self.definition.get("name", "Unknown Device")
        self.sub_devices = [
            SubDeviceTemplate(sub_def) for sub_def in self.definition.get("devices", [])
        ]
        names = [device.name.casefold() for device in self.sub_devices]
        if len(names) != len(set(names)):
            raise ValueError("Device names must be unique within a template")

    async def read_yaml(self):
        async with aiofiles.open(self.file_path, mode="r") as f:
            content = await f.read()
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError as err:
                raise ValueError(f"Invalid YAML: {err}") from err


class SubDeviceTemplate:
    def __init__(self, definition: dict):
        self.definition = definition
        self.name = "Unknown SubDevice"
        self.model = "Unknown Model"
        self.capacity = "Unknown Capacity"
        self.capacity_unit = None
        self.messageIdBindingRegisterOffset = None
        self.readMessageIdRegisterOffset = None
        self.messageIds = []
        self.min_address = None
        self.max_address = None

        self.process_definition()

    def _extract_properties(self):
        """Extract simple properties from definition."""
        self.name = self.definition.get("name", "Unknown SubDevice")
        self.model = self.definition.get("model", "Unknown Model")
        self.capacity = self.definition.get("capacity", "Unknown Capacity")
        self.capacity_unit = self.definition.get("capacity_unit", None)
        self.messageIdBindingRegisterOffset = self.definition.get(
            "bindMessageIdRegisterOffset", None
        )
        self.readMessageIdRegisterOffset = self.definition.get(
            "readMessageIdRegisterOffset", None
        )

    def _process_message_ids(self):
        """Process messageId definitions and convert to addresses."""
        register = self.definition.get("readMessageIdRegisterOffset", None)
        message_addresses = {}
        for register_def in self.definition.get("registers", []):
            if register is None or self.messageIdBindingRegisterOffset is None:
                if "messageId" in register_def:
                    _LOGGER.warning(
                        f"SubDevice {self.name} has register definitions but no readMessageIdRegisterOffset or bindMessageIdRegisterOffset defined. Skipping messageId binding."
                    )
                continue

            if "messageId" in register_def:
                if "address" in register_def:
                    _LOGGER.warning(
                        f"SubDevice {self.name} register definition has both 'address' and 'messageId' defined. 'address' will be ignored."
                    )
                message_id = register_def["messageId"]
                if message_id not in message_addresses:
                    message_addresses[message_id] = register
                    self.messageIds.append(message_id)
                    register += 1
                register_def["address"] = message_addresses[message_id]

    def _calculate_address_range(self):
        """Calculate min/max addresses for all registers."""
        addresses = [
            reg.get("address")
            for reg in self.definition.get("registers", [])
            if "address" in reg
        ]
        if addresses:
            self.min_address = min(addresses)
            self.max_address = max(addresses)

    def process_definition(self):
        self._extract_properties()
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Each device needs a non-empty name")
        registers = self.definition.get("registers", [])
        if not isinstance(registers, list):
            raise ValueError(f"Registers for {self.name} must be a list")
        for reg in registers:
            if not isinstance(reg, dict) or not isinstance(reg.get("name"), str):
                raise ValueError(f"Each register in {self.name} needs a name")
            unsupported = set(reg) - {
                "name",
                "address",
                "messageId",
                "platform",
                "signed",
                "mapping",
                "mask",
                "masks",
                "invert",
                "scale",
                "min",
                "max",
                "step",
                "unit_of_measurement",
                "device_class",
                "state_class",
                "mode",
                "timeout",
            }
            if unsupported:
                raise ValueError(
                    f"Unsupported register options for {self.name} / {reg['name']}: "
                    f"{', '.join(sorted(map(str, unsupported)))}"
                )
            if "signed" in reg and type(reg["signed"]) is not bool:
                raise ValueError(
                    f"signed must be a boolean for {self.name} / {reg['name']}"
                )
            self._validate_masks(reg)
            if "messageId" not in reg and "address" not in reg:
                raise ValueError(
                    f"Register {reg['name']} in {self.name} needs address or messageId"
                )
            for key in ("messageId", "address"):
                if key in reg and (
                    type(reg[key]) is not int or not 0 <= reg[key] <= 65535
                ):
                    raise ValueError(
                        f"Invalid {key} for {self.name} / {reg['name']}: {reg[key]!r}"
                    )
            if "messageId" in reg and (
                self.messageIdBindingRegisterOffset is None
                or self.readMessageIdRegisterOffset is None
            ):
                raise ValueError(
                    f"Message ID register {reg['name']} in {self.name} requires binding and read offsets"
                )
        self._process_message_ids()
        self.validate_binding_count(len(self.messageIds))
        self._calculate_address_range()
        if self.messageIdBindingRegisterOffset is not None:
            start, end = self.binding_data_bounds()
            block_start = 0 if start == 4 else start - 32
            for reg in registers:
                if not block_start <= reg["address"] <= end:
                    raise ValueError(
                        f"Register {reg['name']} in {self.name} has address {reg['address']} "
                        f"outside its device block {block_start}–{end}"
                    )

    def binding_data_bounds(self):
        """MIM-B19N data slots: outdoor 4–49, indoor block offsets 32–49."""
        binding = self.messageIdBindingRegisterOffset
        start = self.readMessageIdRegisterOffset
        if type(binding) is int and type(start) is int:
            if binding == 6000 and start == 4:
                return 4, 49
            if binding == 7000 and 82 <= start <= 2432 and (start - 82) % 50 == 0:
                return start, start + 17
        raise ValueError(
            f"Invalid MIM-B19N binding/read offsets for {self.name}: {binding}/{start}; "
            "expected 6000/4 or 7000/(82 + 50 × indoor unit index 0–47)"
        )

    def validate_binding_count(self, count):
        """Also called before dynamic FSV bindings, before any hardware write."""
        if count == 0 and self.messageIdBindingRegisterOffset is None:
            return
        start, end = self.binding_data_bounds()
        capacity = end - start + 1
        if count > capacity:
            raise ValueError(
                f"{self.name} needs {count} custom registers but only {capacity} fit "
                f"in data addresses {start}–{end}; remove at least {count - capacity} message ID(s)"
            )

    def entity_definitions(self):
        """Expand fields after assigning their shared physical register address."""
        for reg in self.definition.get("registers", []):
            if "masks" not in reg:
                yield reg
                continue
            parent = {key: value for key, value in reg.items() if key != "masks"}
            for field in reg["masks"]:
                yield {**parent, **field, "name": f"{reg['name']} {field['name']}"}

    def _validate_masks(self, reg):
        """Reject ambiguous masks during setup with the register's context."""
        if not any(key in reg for key in ("mask", "masks", "invert")):
            return
        context = f"{self.name} / {reg['name']}"
        if "mapping" in reg:
            raise ValueError(f"Masks cannot be combined with mapping: {context}")
        if "masks" in reg:
            if "mask" in reg or "invert" in reg:
                raise ValueError(
                    f"Put mask and invert inside each masks entry: {context}"
                )
            definitions = reg["masks"]
            if not isinstance(definitions, list) or not definitions:
                raise ValueError(f"masks must be a non-empty list: {context}")
            names = set()
            for definition in definitions:
                if not isinstance(definition, dict):
                    raise ValueError(f"Each masks entry must be an object: {context}")
                name = definition.get("name")
                if not isinstance(name, str) or not slugify(name):
                    raise ValueError(
                        f"Each masks entry needs a non-empty name: {context}"
                    )
                if slugify(name) in names:
                    raise ValueError(f"Duplicate masks entity name {name!r}: {context}")
                names.add(slugify(name))
                if set(definition) - {
                    "name",
                    "mask",
                    "invert",
                    "platform",
                    "min",
                    "max",
                    "step",
                    "scale",
                    "unit_of_measurement",
                    "device_class",
                    "mode",
                    "timeout",
                }:
                    raise ValueError(
                        f"Unsupported masks entry options: {context} / {name}"
                    )
        else:
            definitions = [reg]
        for definition in definitions:
            field = {**reg, **definition}
            platform = field.get("platform", "sensor")
            if platform not in ("binary_sensor", "switch", "number"):
                raise ValueError(
                    f"Masks require binary_sensor, switch or number: {context}"
                )
            mask = definition.get("mask")
            if type(mask) is not int or not 1 <= mask <= 0xFFFF:
                raise ValueError(f"mask must be an integer from 1 to 65535: {context}")
            if "invert" in definition and type(definition["invert"]) is not bool:
                raise ValueError(f"invert must be a boolean: {context}")
            if platform in ("switch", "number"):
                width_mask = mask // (mask & -mask)
                if width_mask & (width_mask + 1):
                    raise ValueError(
                        f"Writable masks must select contiguous bits: {context}"
                    )
                if field.get("signed", False):
                    raise ValueError(
                        f"Writable masked fields must be unsigned: {context}"
                    )
                if platform == "number":
                    if "invert" in field:
                        raise ValueError(
                            f"invert is only supported for boolean fields: {context}"
                        )
                    scale, low, high, step = (
                        field.get("scale", 1),
                        field.get("min", 0),
                        field.get("max", 100),
                        field.get("step", 1),
                    )
                    if not all(
                        type(value) in (int, float) and math.isfinite(value)
                        for value in (scale, low, high, step)
                    ) or not (
                        scale > 0
                        and step > 0
                        and 0 <= low <= high <= width_mask * scale
                    ):
                        raise ValueError(
                            f"Invalid number range, scale or step for mask {mask:#06x}: {context}"
                        )

    def get_final_message_ids(self, additional_ids: list[int] = None) -> list[int]:
        """Merge message IDs with additional ones."""
        final_ids = list(self.messageIds)
        if additional_ids:
            for msg_id in additional_ids:
                if msg_id not in final_ids:
                    final_ids.append(msg_id)
        return final_ids
