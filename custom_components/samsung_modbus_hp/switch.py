from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import SamsungModbusEntity

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        SamsungModbusSwitch(coordinator, sub_device, reg, entry.entry_id)
        for sub_device in coordinator.device_template.sub_devices
        for reg in sub_device.definition.get("registers", [])
        if reg.get("platform") == "switch"
    ]
    async_add_entities(entities)

class SamsungModbusSwitch(SamsungModbusEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        return bool(raw_val) if raw_val is not None else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.client.write_register(self.register_def["address"], 1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.client.write_register(self.register_def["address"], 0)
        await self.coordinator.async_request_refresh()
