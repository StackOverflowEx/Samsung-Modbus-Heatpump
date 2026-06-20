from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN

class SamsungModbusEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, sub_device, register_def, entry_id: str):
        super().__init__(coordinator)
        self.sub_device = sub_device
        self.register_def = register_def
        self._entry_id = entry_id
        
        safe_sub_name = slugify(sub_device.name)
        safe_reg_name = slugify(register_def['name'])
        self._attr_unique_id = f"{entry_id}_{safe_sub_name}_{safe_reg_name}"
        self._attr_name = register_def["name"]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self.sub_device.name}")},
            name=self.sub_device.name,
            model=self.sub_device.model,
            manufacturer="Samsung" 
        )
        
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    def _get_raw_value(self) -> int | None:
        data = self.coordinator.data.get(self.sub_device)
        if not data or not hasattr(data, "registers"): 
            return None
            
        idx = self.register_def["address"] - self.sub_device.min_address
        if idx < 0 or idx >= len(data.registers): 
            return None
            
        return data.registers[idx]
