import aiofiles
import yaml
import logging
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
        self._calculate_address_range()

    def _validate_masks(self, reg):
        """Reject ambiguous masks during setup with the register's context."""
        if not any(key in reg for key in ("mask", "masks", "invert")):
            return
        context = f"{self.name} / {reg['name']}"
        if reg.get("platform", "sensor") != "binary_sensor":
            raise ValueError(f"Masks are only supported for binary_sensor: {context}")
        if "bits" in reg or "mapping" in reg:
            raise ValueError(
                f"Masks cannot be combined with bits or mapping: {context}"
            )
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
                if set(definition) - {"name", "mask", "invert"}:
                    raise ValueError(
                        f"Masks entries only accept name, mask and invert: {context}"
                    )
        else:
            definitions = [reg]
        for definition in definitions:
            mask = definition.get("mask")
            if type(mask) is not int or not 1 <= mask <= 0xFFFF:
                raise ValueError(f"mask must be an integer from 1 to 65535: {context}")
            if "invert" in definition and type(definition["invert"]) is not bool:
                raise ValueError(f"invert must be a boolean: {context}")

    def get_final_message_ids(self, additional_ids: list[int] = None) -> list[int]:
        """Merge message IDs with additional ones."""
        final_ids = list(self.messageIds)
        if additional_ids:
            for msg_id in additional_ids:
                if msg_id not in final_ids:
                    final_ids.append(msg_id)
        return final_ids
