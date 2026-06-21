from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from .entity import SamsungModbusEntity, async_setup_platform_entry

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    await async_setup_platform_entry(hass, entry, async_add_entities, "switch", SamsungModbusSwitch)

class SamsungModbusSwitch(SamsungModbusEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        return bool(raw_val) if raw_val is not None else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_write_modbus_register(1)

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_write_modbus_register(0)
