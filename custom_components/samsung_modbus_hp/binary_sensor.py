from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import slugify

from .entity import SamsungModbusEntity, async_setup_platform_entry, BitExtractorMixin


def binary_sensor_factory(coordinator, sub_device, reg, entry_id):
    if "masks" in reg:
        return [
            SamsungModbusBinarySensor(
                coordinator,
                sub_device,
                {
                    **{key: value for key, value in reg.items() if key != "masks"},
                    **mask_def,
                    "name": f"{reg['name']} {mask_def['name']}",
                },
                entry_id,
            )
            for mask_def in reg["masks"]
        ]
    if "bits" in reg:
        return [
            SamsungModbusBitSensor(coordinator, sub_device, reg, bit_def, entry_id)
            for bit_def in reg["bits"]
        ]
    return [SamsungModbusBinarySensor(coordinator, sub_device, reg, entry_id)]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    await async_setup_platform_entry(
        hass, entry, async_add_entities, "binary_sensor", None, binary_sensor_factory
    )


class SamsungModbusBinarySensor(SamsungModbusEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        if raw_val is None:
            return None

        if "mask" in self.register_def:
            is_set = bool(raw_val & self.register_def["mask"])
            return not is_set if self.register_def.get("invert", False) else is_set

        mapping = self.register_def.get("mapping", {})
        if mapping:
            value = self._get_mapped_value(
                raw_val, mapping, as_string=False, report_recovery=False
            )
            if value is None:
                return None
            if isinstance(value, bool):
                self._report_value_problem(None)
                return value
            if str(value).lower() in ("on", "off"):
                self._report_value_problem(None)
                return str(value).lower() == "on"
            self._report_value_problem(
                "invalid_binary",
                f"Mapped value {value!r} is not On/Off or a boolean; state is unknown",
            )
            return None
        return bool(raw_val)


class SamsungModbusBitSensor(
    BitExtractorMixin, SamsungModbusEntity, BinarySensorEntity
):
    def __init__(self, coordinator, sub_device, register_def, bit_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        self.bit_def = bit_def
        self._attr_unique_id = f"{self._attr_unique_id}_{slugify(bit_def['name'])}"
        self._attr_name = f"{register_def['name']} - {bit_def['name']}"

    @property
    def is_on(self) -> bool | None:
        return self._is_bit_set(self.bit_def["bit"])
