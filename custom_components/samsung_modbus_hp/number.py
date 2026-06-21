from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode

from .entity import SamsungModbusEntity, async_setup_platform_entry
from .utils import calculate_display_precision

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    await async_setup_platform_entry(hass, entry, async_add_entities, "number", SamsungModbusNumber)

class SamsungModbusNumber(SamsungModbusEntity, NumberEntity):
    def __init__(self, coordinator, sub_device, register_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        
        self._scale = register_def.get("scale", 1.0)
        
        self._attr_native_min_value = register_def.get("min", 0)
        self._attr_native_max_value = register_def.get("max", 100)
        self._attr_native_step = register_def.get("step", 1)
        
        self._attr_native_unit_of_measurement = register_def.get("unit_of_measurement")
        self._attr_device_class = register_def.get("device_class")
        self._attr_state_class = register_def.get("state_class")
        
        self._attr_suggested_display_precision = calculate_display_precision(self._scale)

        yaml_mode = register_def.get("mode", "box").lower()
        if yaml_mode == "slider":
            self._attr_mode = NumberMode.SLIDER
        elif yaml_mode == "auto":
            self._attr_mode = NumberMode.AUTO
        else:
            self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float | None:
        raw_val = self._get_raw_value()
        if raw_val is not None:
            return round(float(raw_val) * self._scale, self._attr_suggested_display_precision)
        return None

    async def async_set_native_value(self, value: float) -> None:
        write_val = int(round(value / self._scale))
        await self.async_write_modbus_register(write_val)
