"""Actions for FSV writes and template reloads."""

import json
import logging
import os

import aiofiles
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
SERVICE_SET_FSV = "set_field_setting_value"
SERVICE_RELOAD = "reload"


async def load_fsv_mapping():
    path = os.path.join(os.path.dirname(__file__), "fsv_mapping.json")
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as file:
            mapping = json.loads(await file.read())
        if not isinstance(mapping, dict) or not all(
            type(value) is int and 0 <= value <= 65535 for value in mapping.values()
        ):
            raise ValueError(
                "Expected an object mapping FSV codes to integer message IDs from 0 to 65535"
            )
        return mapping
    except (OSError, ValueError) as err:
        raise HomeAssistantError(f"Cannot load FSV mapping {path}: {err}") from err


def _entry_ids(hass, entry_id=None):
    """Include configured entries, even when setup failed, so reload can recover."""
    entries = hass.config_entries.async_entries(DOMAIN)
    ids = [entry.entry_id for entry in entries]
    if entry_id is not None:
        if entry_id not in ids:
            raise ServiceValidationError(
                f"Unknown Samsung Modbus configuration entry {entry_id!r}"
            )
        return [entry_id]
    if not ids:
        raise ServiceValidationError("No Samsung Modbus configuration entries found")
    return ids


async def async_setup_services(hass: HomeAssistant):
    if hass.services.has_service(DOMAIN, SERVICE_SET_FSV):
        return

    async def handle_set_fsv(call: ServiceCall):
        unit_name = str(call.data.get("unit_name", "")).strip()
        fsv_code = str(call.data.get("fsv_code", "")).strip()
        raw_value = call.data.get("value")
        try:
            if not unit_name or not fsv_code:
                raise ServiceValidationError("unit_name and fsv_code are required")
            try:
                value = int(raw_value)
            except (TypeError, ValueError, OverflowError) as err:
                raise ServiceValidationError(
                    "value must be an integer from 0 to 65535"
                ) from err
            if (
                isinstance(raw_value, bool)
                or (isinstance(raw_value, float) and raw_value != value)
                or not 0 <= value <= 65535
            ):
                raise ServiceValidationError(
                    "value must be an integer from 0 to 65535; fractional values are not supported"
                )
            mapping = await load_fsv_mapping()
            if fsv_code not in mapping:
                raise ServiceValidationError(
                    f"FSV code {fsv_code!r} not found in fsv_mapping.json"
                )
            ids = _entry_ids(hass, call.data.get("entry_id"))
            candidates = [
                coordinator
                for entry_id in ids
                if (coordinator := hass.data.get(DOMAIN, {}).get(entry_id)) is not None
                and any(
                    sd.name.casefold() == unit_name.casefold()
                    for sd in coordinator.device_template.sub_devices
                )
            ]
            if not candidates:
                raise ServiceValidationError(
                    f"Target unit {unit_name!r} not found in a loaded integration; check the unit name and entry_id"
                )
            if len(candidates) > 1:
                raise ServiceValidationError(
                    f"Multiple integrations contain unit {unit_name!r}; specify entry_id"
                )
            await candidates[0].async_write_fsv(unit_name, mapping[fsv_code], value)
        except HomeAssistantError as err:
            _LOGGER.error(
                "FSV write failed (unit %r, FSV %r, value %r): %s",
                unit_name,
                fsv_code,
                raw_value,
                err,
            )
            raise
        _LOGGER.info(
            "FSV %s write accepted for %s (raw value %s)", fsv_code, unit_name, value
        )

    async def handle_reload(call: ServiceCall):
        try:
            for entry_id in _entry_ids(hass, call.data.get("entry_id")):
                _LOGGER.info(
                    "Reloading Samsung Modbus configuration %s and its device template",
                    entry_id,
                )
                if not await hass.config_entries.async_reload(entry_id):
                    raise HomeAssistantError(
                        f"Reload failed for configuration {entry_id}; see integration logs"
                    )
        except HomeAssistantError as err:
            _LOGGER.error("Samsung Modbus reload failed: %s", err)
            raise

    hass.services.async_register(DOMAIN, SERVICE_SET_FSV, handle_set_fsv)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, handle_reload)
