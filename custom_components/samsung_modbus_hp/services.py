"""Actions for FSV writes, heating/cooling curves and template reloads."""

import json
import logging
import os
from decimal import Decimal, DecimalException, Inexact, InvalidOperation, localcontext
import math

import aiofiles
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
SERVICE_SET_FSV = "set_field_setting_value"
SERVICE_RELOAD = "reload"
SERVICE_SET_HEATING_CURVE = "set_heating_curve"

# Outdoor lower/upper, then water at upper/lower outdoor endpoints.
# Keep the endpoint-to-FSV mapping fixed even for reversed cooling curves.
CURVE_CODES = {
    "heating_1": ("2011", "2012", "2022", "2021"),
    "heating_2": ("2011", "2012", "2032", "2031"),
    "cooling_1": ("2051", "2052", "2062", "2061"),
    "cooling_2": ("2051", "2052", "2072", "2071"),
}
TEMPERATURE_FIELDS = (
    "outdoor_temperature_lower",
    "outdoor_temperature_upper",
    "water_temperature_at_upper_outdoor",
    "water_temperature_at_lower_outdoor",
)


def _integer(value, name, lower, upper):
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ServiceValidationError(
            f"{name} must be an integer from {lower} to {upper}"
        ) from err
    if (
        isinstance(value, bool)
        or (not isinstance(value, str) and value != result)
        or not lower <= result <= upper
    ):
        raise ServiceValidationError(
            f"{name} must be an integer from {lower} to {upper}"
        )
    return result


def _validate_fsv_mapping(mapping):
    """Scale is the multiplier from raw protocol units to user units."""
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Expected a non-empty object of FSV definitions")
    for code, definition in mapping.items():
        required = {
            "messageId",
            "scale",
            "signed",
        }
        if (
            not isinstance(definition, dict)
            or not required <= definition.keys()
            or set(definition) - (required | {"options"})
        ):
            raise ValueError(f"FSV {code} requires messageId, scale and signed")
        message_id = definition["messageId"]
        if type(message_id) is not int or not 0 <= message_id <= 65535:
            raise ValueError(f"Invalid messageId for FSV {code}")
        scale, signed = definition["scale"], definition["signed"]
        if (
            type(scale) not in (int, float)
            or not math.isfinite(scale)
            or scale <= 0
            or type(signed) is not bool
        ):
            raise ValueError(f"Invalid scale or signed flag for FSV {code}")
        if "options" in definition:
            options = definition["options"]
            if (
                not isinstance(options, list)
                or any(
                    type(value) is not int or not 0 <= value <= 65535
                    for value in options
                )
                or len(options) != len(set(options))
                or scale != 1
                or signed
            ):
                raise ValueError(f"Invalid enum options for FSV {code}")
    return mapping


def _encode_fsv_value(value, definition, disable_postprocessing=False):
    """Convert user units to an exact 16-bit word, without silent rounding."""
    try:
        if isinstance(value, bool):
            raise ValueError
        numeric = Decimal(str(value))
        if not numeric.is_finite():
            raise ValueError
    except (InvalidOperation, ValueError) as err:
        raise ServiceValidationError("FSV value must be a finite number") from err

    if disable_postprocessing:
        raw = numeric
    else:
        try:
            with localcontext() as context:
                context.traps[Inexact] = True
                raw = numeric / Decimal(str(definition["scale"]))
        except DecimalException as err:
            raise ServiceValidationError(
                "FSV value cannot be converted exactly within the register range"
            ) from err

    if raw != raw.to_integral_value():
        raise ServiceValidationError(
            "FSV value cannot be represented as a whole register value; "
            "check the scaling or supply a whole value when postprocessing is disabled"
        )
    # Raw mode also accepts an already encoded unsigned word. Negative raw
    # inputs are allowed only when the source explicitly declares signed data.
    signed = definition["signed"] is True
    lower = -32768 if signed else 0
    upper = 32767 if signed and not disable_postprocessing else 65535
    if not lower <= raw <= upper:
        raise ServiceValidationError(
            f"FSV value is outside its register range after conversion ({lower} to {upper})"
        )
    if not disable_postprocessing and "options" in definition:
        options = definition["options"] or [0, 1]
        if int(raw) not in options:
            raise ServiceValidationError(
                f"Invalid enum FSV value {value!r}; valid options: {', '.join(map(str, options))}"
            )
    return int(raw) & 0xFFFF


def _resolve_unit(hass, data):
    """Resolve exactly one loaded unit using its Home Assistant device ID."""
    device_id = data["device_id"]
    registry_device = dr.async_get(hass).async_get(device_id)
    if registry_device is None:
        raise ServiceValidationError(f"Unknown device {device_id!r}")
    candidates = []
    for entry_id in registry_device.config_entries:
        coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None:
            continue
        for sub_device in coordinator.device_template.sub_devices:
            if (DOMAIN, f"{entry_id}_{sub_device.name}") in registry_device.identifiers:
                candidates.append((coordinator, sub_device))
    if len(candidates) != 1:
        raise ServiceValidationError(
            "Select a device belonging to one loaded Samsung Modbus unit"
        )
    return candidates[0]


async def load_fsv_mapping():
    path = os.path.join(os.path.dirname(__file__), "fsv_mapping.json")
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as file:
            mapping = json.loads(await file.read())
        return _validate_fsv_mapping(mapping)
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
        unit_name = None
        fsv_code = str(call.data.get("fsv_code", "")).strip()
        raw_value = call.data.get("value")
        try:
            if not fsv_code:
                raise ServiceValidationError("fsv_code is required")
            mapping = await load_fsv_mapping()
            if fsv_code not in mapping:
                raise ServiceValidationError(
                    f"FSV code {fsv_code!r} not found in fsv_mapping.json"
                )
            definition = mapping[fsv_code]
            value = _encode_fsv_value(
                raw_value, definition, call.data["disable_postprocessing"]
            )
            coordinator, sub_device = _resolve_unit(hass, call.data)
            unit_name = sub_device.name
            await coordinator.async_write_fsv(unit_name, definition["messageId"], value)
        except HomeAssistantError as err:
            _LOGGER.error(
                "FSV write failed (unit %r, device %r, FSV %r, value %r): %s",
                unit_name,
                call.data.get("device_id"),
                fsv_code,
                raw_value,
                err,
            )
            raise
        _LOGGER.info(
            "FSV %s write accepted for %s (input %s, raw value %s, postprocessing %s)",
            fsv_code,
            unit_name,
            raw_value,
            value,
            not call.data["disable_postprocessing"],
        )

    async def handle_set_heating_curve(call: ServiceCall):
        curve = call.data["curve"]
        try:
            heating = curve.startswith("heating")
            ranges = (
                ((-20, 5), (10, 20), (17, 75), (17, 75))
                if heating
                else ((25, 35), (35, 45), (5, 25), (5, 25))
            )
            temperatures = [
                _integer(call.data[field], field, *limits)
                for field, limits in zip(TEMPERATURE_FIELDS, ranges, strict=True)
            ]
            outdoor_low, outdoor_high, water_at_warm, water_at_cold = temperatures
            if outdoor_low >= outdoor_high:
                raise ServiceValidationError(
                    "Lower outdoor temperature must be below upper outdoor temperature"
                )
            if heating and water_at_cold <= water_at_warm:
                cold_code, warm_code = CURVE_CODES[curve][3], CURVE_CODES[curve][2]
                raise ServiceValidationError(
                    f"Heating requires FSV {cold_code} > {warm_code}: water temperature "
                    "at the lower outdoor endpoint must be strictly higher than "
                    "at the upper outdoor endpoint"
                )
            mapping = await load_fsv_mapping()
            codes = CURVE_CODES[curve]
            missing = [code for code in codes if code not in mapping]
            if missing:
                raise ServiceValidationError(
                    f"FSV codes missing from fsv_mapping.json: {', '.join(missing)}"
                )
            settings = [
                (
                    mapping[code]["messageId"],
                    _encode_fsv_value(
                        value, mapping[code], call.data["disable_postprocessing"]
                    ),
                )
                for code, value in zip(codes, temperatures, strict=True)
            ]
            coordinator, sub_device = _resolve_unit(hass, call.data)
            _LOGGER.warning(
                "Setting %s for %s: outdoor endpoints affect BOTH %s curves",
                curve,
                sub_device.name,
                "heating" if heating else "cooling",
            )
            if heating and max(water_at_cold, water_at_warm) > 65:
                _LOGGER.warning(
                    "Heating water temperature above 65°C requested for %s; "
                    "70/75°C is supported only by some outdoor unit models",
                    sub_device.name,
                )
            if curve == "cooling_1" and min(water_at_cold, water_at_warm) < 16:
                _LOGGER.warning(
                    "Cooling 1 below 16°C requested for %s; the manual warns "
                    "against this for underfloor cooling due to condensation",
                    sub_device.name,
                )
            if not heating and water_at_cold <= water_at_warm:
                _LOGGER.warning(
                    "Non-descending cooling curve %s for %s: water at lower outdoor "
                    "temperature (%s°C) is not higher than at upper outdoor temperature "
                    "(%s°C). Proceeding; model support is not verified and this does "
                    "not provide indoor dew-point/condensation protection",
                    curve,
                    sub_device.name,
                    water_at_cold,
                    water_at_warm,
                )
            await coordinator.async_write_fsvs(sub_device.name, settings)
        except HomeAssistantError as err:
            _LOGGER.error(
                "Setting curve %s for device %r failed: %s",
                curve,
                call.data.get("device_id"),
                err,
            )
            raise
        _LOGGER.info("All four %s FSV writes accepted for %s", curve, sub_device.name)

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FSV,
        handle_set_fsv,
        schema=vol.Schema(
            {
                vol.Required("device_id"): str,
                vol.Required("fsv_code"): vol.Any(str, int),
                vol.Required("value"): object,
                vol.Optional("disable_postprocessing", default=False): bool,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HEATING_CURVE,
        handle_set_heating_curve,
        schema=vol.Schema(
            {
                vol.Required("device_id"): str,
                vol.Required("curve"): vol.In(CURVE_CODES),
                vol.Optional("disable_postprocessing", default=False): bool,
                **{vol.Required(field): object for field in TEMPERATURE_FIELDS},
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, handle_reload)
