from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .entity import SamsungModbusEntity, async_setup_platform_entry, BitExtractorMixin
from .utils import get_mapped_value

def binary_sensor_factory(coordinator, sub_device, reg, entry_id):
    if "bits" in reg:
        return [SamsungModbusBitSensor(coordinator, sub_device, reg, bit_def, entry_id) for bit_def in reg["bits"]]
    return [SamsungModbusBinarySensor(coordinator, sub_device, reg, entry_id)]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    await async_setup_platform_entry(hass, entry, async_add_entities, "binary_sensor", None, binary_sensor_factory)

class SamsungModbusBinarySensor(SamsungModbusEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
        
        mapping = self.register_def.get("mapping", {})
        if mapping:
            return get_mapped_value(raw_val, mapping, as_string=False) == "On"
        return bool(raw_val)

class SamsungModbusBitSensor(BitExtractorMixin, SamsungModbusEntity, BinarySensorEntity):
    def __init__(self, coordinator, sub_device, register_def, bit_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        self.bit_def = bit_def
        self._attr_unique_id = f"{self._attr_unique_id}_{slugify(bit_def['name'])}"
        self._attr_name = f"{register_def['name']} - {bit_def['name']}"

    @property
    def is_on(self) -> bool | None:
        return self._is_bit_set(self.bit_def["bit"])
