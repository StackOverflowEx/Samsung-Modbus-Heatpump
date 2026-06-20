from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .entity import SamsungModbusEntity

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SamsungModbusNumber(coordinator, sub_device, reg, entry.entry_id)
        for sub_device in coordinator.device_template.sub_devices
        for reg in sub_device.definition.get("registers", [])
        if reg.get("platform") == "number"
    ]
    async_add_entities(entities)

class SamsungModbusNumber(SamsungModbusEntity, NumberEntity):
    def __init__(self, coordinator, sub_device, register_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        
        self._scale = register_def.get("scale", 1.0)
        self._attr_native_min_value = register_def.get("min", 0) * self._scale
        self._attr_native_max_value = register_def.get("max", 100) * self._scale
        self._attr_native_step = register_def.get("step", 1) * self._scale
        
        self._attr_native_unit_of_measurement = register_def.get("unit_of_measurement")
        self._attr_device_class = register_def.get("device_class")
        self._attr_state_class = register_def.get("state_class")
        
        scale_str = str(self._scale)
        if "." in scale_str:
            decimals = scale_str.split(".")[1]
            self._attr_suggested_display_precision = 0 if decimals == "0" else len(decimals)
        else:
            self._attr_suggested_display_precision = 0

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
        await self.coordinator.client.write_register(self.register_def["address"], write_val)
        await self.coordinator.async_request_refresh()
