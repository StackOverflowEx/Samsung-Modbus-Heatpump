from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .entity import SamsungModbusEntity

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    for sub_device in coordinator.device_template.sub_devices:
        for reg in sub_device.definition.get("registers", []):
            if reg.get("platform") == "binary_sensor":
                if "bits" in reg:
                    for bit_def in reg["bits"]:
                        entities.append(SamsungModbusBitSensor(coordinator, sub_device, reg, bit_def, entry.entry_id))
                else:
                    entities.append(SamsungModbusBinarySensor(coordinator, sub_device, reg, entry.entry_id))
    async_add_entities(entities)

class SamsungModbusBinarySensor(SamsungModbusEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
        
        mapping = self.register_def.get("mapping", {})
        if mapping:
            return mapping.get(raw_val, mapping.get("fallback")) == "On"
        return bool(raw_val)

class SamsungModbusBitSensor(SamsungModbusEntity, BinarySensorEntity):
    def __init__(self, coordinator, sub_device, register_def, bit_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        self.bit_def = bit_def
        self._attr_unique_id = f"{self._attr_unique_id}_{slugify(bit_def['name'])}"
        self._attr_name = f"{register_def['name']} - {bit_def['name']}"

    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        if raw_val is None:
            return None
        return bool(raw_val & (1 << self.bit_def["bit"]))
