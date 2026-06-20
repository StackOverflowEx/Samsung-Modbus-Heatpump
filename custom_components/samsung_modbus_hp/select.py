from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity

from .const import DOMAIN
from .entity import SamsungModbusEntity

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SamsungModbusSelect(coordinator, sub_device, reg, entry.entry_id)
        for sub_device in coordinator.device_template.sub_devices
        for reg in sub_device.definition.get("registers", [])
        if reg.get("platform") == "select"
    ]
    async_add_entities(entities)

class SamsungModbusSelect(SamsungModbusEntity, SelectEntity):
    def __init__(self, coordinator, sub_device, register_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        
        self._mapping = register_def.get("mapping", {})
        self._attr_options = [str(val) for key, val in self._mapping.items() if key != "fallback"]

    @property
    def current_option(self) -> str | None:
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
            
        if raw_val in self._mapping: 
            return str(self._mapping[raw_val])
            
        fallback = self._mapping.get("fallback")
        return fallback.format(value=raw_val) if fallback else None

    async def async_select_option(self, option: str) -> None:
        write_val = next(
            (int(key) for key, val in self._mapping.items() if str(val) == option and key != "fallback"), 
            None
        )
        if write_val is not None:
            await self.coordinator.client.write_register(self.register_def["address"], write_val)
            await self.coordinator.async_request_refresh()
