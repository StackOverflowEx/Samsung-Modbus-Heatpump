from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from .entity import SamsungModbusEntity, async_setup_platform_entry


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    await async_setup_platform_entry(
        hass, entry, async_add_entities, "switch", SamsungModbusSwitch
    )


class SamsungModbusSwitch(SamsungModbusEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_field_value()
        if raw_val is None:
            return None
        return (
            not bool(raw_val)
            if self.register_def.get("invert", False)
            else bool(raw_val)
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self.async_write_modbus_register(
            0 if self.register_def.get("invert", False) else 1
        )

    async def async_turn_off(self, **kwargs) -> None:
        await self.async_write_modbus_register(
            1 if self.register_def.get("invert", False) else 0
        )
