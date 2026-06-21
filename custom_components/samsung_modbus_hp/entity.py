from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import slugify
from homeassistant.const import CONF_SCAN_INTERVAL

from .const import DOMAIN

async def async_setup_platform_entry(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback,
    platform_name: str,
    entity_class,
    entity_factory_func=None
) -> None:
    """Generic setup for all platform types."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    for sub_device in coordinator.device_template.sub_devices:
        for reg in sub_device.definition.get("registers", []):
            if reg.get("platform", "sensor") == platform_name:
                if entity_factory_func:
                    entities.extend(entity_factory_func(coordinator, sub_device, reg, entry.entry_id))
                else:
                    entities.append(entity_class(coordinator, sub_device, reg, entry.entry_id))
    
    async_add_entities(entities)

class BitExtractorMixin:
    """Handles bit extraction from register values."""
    def _get_active_bits(self) -> list[dict]:
        """Get active bit definitions from current register value."""
        raw_val = self._get_raw_value()
        if raw_val is None:
            return []
        return [
            bit_def 
            for bit_def in self.register_def.get("bits", [])
            if raw_val & (1 << bit_def["bit"])
        ]
    
    def _is_bit_set(self, bit_index: int) -> bool:
        """Check if specific bit is set."""
        raw_val = self._get_raw_value()
        return bool(raw_val & (1 << bit_index)) if raw_val is not None else False

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
        if not data or not isinstance(data, dict): 
            return None
            
        target_address = self.register_def.get("address")
        return data.get(target_address)

    async def async_write_modbus_register(self, value: int) -> None:
        """Helper to write to Modbus and apply optimistic UI masking."""
        target_address = self.register_def["address"]
        
        scan_interval = self.coordinator.entry.options.get(CONF_SCAN_INTERVAL, 30)
        custom_timeout = self.register_def.get("timeout", scan_interval)
        
        await self.coordinator.async_write_register(
            target_address, value, self.sub_device, custom_timeout
        )
        
        self.async_write_ha_state()
