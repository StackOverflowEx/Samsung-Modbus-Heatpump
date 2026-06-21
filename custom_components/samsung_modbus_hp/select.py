from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.select import SelectEntity

from .entity import SamsungModbusEntity, async_setup_platform_entry
from .utils import get_mapped_value, extract_options_from_mapping

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    await async_setup_platform_entry(hass, entry, async_add_entities, "select", SamsungModbusSelect)

class SamsungModbusSelect(SamsungModbusEntity, SelectEntity):
    def __init__(self, coordinator, sub_device, register_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        
        self._mapping = register_def.get("mapping", {})
        self._attr_options = extract_options_from_mapping(self._mapping)

    @property
    def current_option(self) -> str | None:
        raw_val = self._get_raw_value()
        return get_mapped_value(raw_val, self._mapping)

    async def async_select_option(self, option: str) -> None:
        write_val = next(
            (int(key) for key, val in self._mapping.items() if str(val) == option and key != "fallback"), 
            None
        )
        if write_val is not None:
            await self.async_write_modbus_register(write_val)
