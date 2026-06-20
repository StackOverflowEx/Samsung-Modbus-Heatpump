from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.util import slugify

from .const import DOMAIN
from .entity import SamsungModbusEntity

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    for sub_device in coordinator.device_template.sub_devices:
        # Diagnostic Sensors
        entities.append(SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Update Interval", "interval"))
        entities.append(SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Model", "model"))
        entities.append(SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Capacity", "capacity"))
        entities.append(SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Read Duration", "duration"))

        # Standard Sensors
        for reg in sub_device.definition.get("registers", []):
            platform = reg.get("platform", "sensor")
            if platform == "sensor":
                if "bits" in reg:
                    entities.append(SamsungModbusBitListSensor(coordinator, sub_device, reg, entry.entry_id))
                else:
                    entities.append(SamsungModbusSensor(coordinator, sub_device, reg, entry.entry_id))
                    
    async_add_entities(entities)

class SamsungModbusDiagnosticSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, sub_device, entry_id, name, sensor_type):
        super().__init__(coordinator)
        self.sub_device = sub_device
        self._entry_id = entry_id
        self._sensor_type = sensor_type
        
        safe_sub_name = slugify(sub_device.name)
        safe_name = slugify(name)
        self._attr_unique_id = f"{entry_id}_{safe_sub_name}_{safe_name}"
        self._attr_name = name

        if sensor_type in ["interval", "duration"]:
            self._attr_native_unit_of_measurement = "s"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_{self.sub_device.name}")},
            name=self.sub_device.name,
            model=self.sub_device.model,
            manufacturer="Samsung"
        )

    @property
    def native_value(self):
        if self._sensor_type == "interval":
            intervals = getattr(self.coordinator, "measured_interval", {})
            val = intervals.get(self.sub_device.name, 0)
            return round(val, 1)
            
        elif self._sensor_type == "duration":
            durations = getattr(self.coordinator, "read_durations", {})
            val = durations.get(self.sub_device.name, 0)
            return round(val, 3) 
            
        elif self._sensor_type == "model":
            return self.sub_device.model
            
        elif self._sensor_type == "capacity":
            return f"{self.sub_device.capacity} {self.sub_device.capacity_unit}"
            
        return None

class SamsungModbusSensor(SamsungModbusEntity, SensorEntity):
    def __init__(self, coordinator, sub_device, register_def, entry_id):
        super().__init__(coordinator, sub_device, register_def, entry_id)
        
        self._attr_native_unit_of_measurement = register_def.get("unit_of_measurement")
        self._attr_device_class = register_def.get("device_class")
        self._attr_state_class = register_def.get("state_class")
        self._scale = register_def.get("scale", 1.0)
        
        scale_str = str(self._scale)
        if "." in scale_str:
            decimals = scale_str.split(".")[1]
            self._attr_suggested_display_precision = 0 if decimals == "0" else len(decimals)
        else:
            self._attr_suggested_display_precision = 0

        mapping = register_def.get("mapping")
        if mapping:
            options_set = {str(v) for k, v in mapping.items() if k != "fallback"}
            self._attr_options = list(options_set)
            
            if not self._attr_device_class:
                self._attr_device_class = "enum"

    @property
    def native_value(self):
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
            
        mapping = self.register_def.get("mapping")
        if mapping:
            if raw_val in mapping: 
                return str(mapping[raw_val])
            if "fallback" in mapping: 
                return str(mapping["fallback"].format(value=raw_val))
                
        if self._scale != 1.0:
            return round(float(raw_val) * self._scale, self._attr_suggested_display_precision)
            
        return raw_val

class SamsungModbusBitListSensor(SamsungModbusEntity, SensorEntity):
    @property
    def native_value(self):
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
        
        active_bits = [
            bit_def["name"] 
            for bit_def in self.register_def.get("bits", [])
            if raw_val & (1 << bit_def["bit"])
        ]
                
        return ", ".join(active_bits) if active_bits else "OK"
