from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import SamsungModbusEntity, async_setup_platform_entry


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    await async_setup_platform_entry(
        hass, entry, async_add_entities, "binary_sensor", SamsungModbusBinarySensor
    )


class SamsungModbusBinarySensor(SamsungModbusEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        raw_val = self._get_raw_value()
        if raw_val is None:
            return None

        if "mask" in self.register_def:
            is_set = bool(raw_val & self.register_def["mask"])
            return not is_set if self.register_def.get("invert", False) else is_set

        mapping = self.register_def.get("mapping", {})
        if mapping:
            value = self._get_mapped_value(
                raw_val, mapping, as_string=False, report_recovery=False
            )
            if value is None:
                return None
            if isinstance(value, bool):
                self._report_value_problem(None)
                return value
            if str(value).lower() in ("on", "off"):
                self._report_value_problem(None)
                return str(value).lower() == "on"
            self._report_value_problem(
                "invalid_binary",
                f"Mapped value {value!r} is not On/Off or a boolean; state is unknown",
            )
            return None
        return bool(raw_val)
