from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.util import slugify

from .const import DOMAIN
from .entity import SamsungModbusEntity, async_setup_platform_entry, BitExtractorMixin
from .utils import calculate_display_precision, get_mapped_value, extract_options_from_mapping

def sensor_factory(coordinator, sub_device, reg, entry_id):
    if "bits" in reg:
        return [SamsungModbusBitListSensor(coordinator, sub_device, reg, entry_id)]
    return [SamsungModbusSensor(coordinator, sub_device, reg, entry_id)]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    # Add diagnostic sensors
    diag_entities = []
    for sub_device in coordinator.device_template.sub_devices:
        diag_entities.extend([
            SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Update Interval", "interval"),
            SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Model", "model"),
            SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Capacity", "capacity"),
            SamsungModbusDiagnosticSensor(coordinator, sub_device, entry.entry_id, "Read Duration", "duration")
        ])
    async_add_entities(diag_entities)

    # Setup standard sensors
    await async_setup_platform_entry(hass, entry, async_add_entities, "sensor", None, sensor_factory)

class SamsungModbusDiagnosticSensor(SamsungModbusEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, sub_device, entry_id, name, sensor_type):
        super().__init__(coordinator, sub_device, {"name": name}, entry_id)
        self._sensor_type = sensor_type

        if sensor_type in ["interval", "duration"]:
            self._attr_native_unit_of_measurement = "s"

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
        
        self._attr_suggested_display_precision = calculate_display_precision(self._scale)

        mapping = register_def.get("mapping")
        if mapping:
            self._attr_options = extract_options_from_mapping(mapping)
            if not self._attr_device_class:
                self._attr_device_class = "enum"

    @property
    def native_value(self):
        raw_val = self._get_raw_value()
        if raw_val is None: 
            return None
            
        mapping = self.register_def.get("mapping")
        if mapping:
            return get_mapped_value(raw_val, mapping)
                
        if self._scale != 1.0:
            return round(float(raw_val) * self._scale, self._attr_suggested_display_precision)
            
        return raw_val

class SamsungModbusBitListSensor(BitExtractorMixin, SamsungModbusEntity, SensorEntity):
    @property
    def native_value(self):
        active_bits = [bit["name"] for bit in self._get_active_bits()]
        return ", ".join(active_bits) if active_bits else "OK"
