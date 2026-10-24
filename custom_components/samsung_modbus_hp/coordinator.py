"""Coordinate serialized Modbus reads, bindings and writes."""

import asyncio
from datetime import timedelta
import logging
import os
import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_DEVICE_ID,
    CONF_SCAN_INTERVAL,
    CONF_FILENAME,
)
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device_template import DeviceTemplate

_LOGGER = logging.getLogger(__name__)


class SamsungModbusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, 30)
            ),
        )
        self.entry = entry
        self.last_poll_time = {}
        self.measured_interval = {}
        self.read_durations = {}
        self.pending_writes = {}
        self._io_lock = asyncio.Lock()
        self.device_id = entry.options.get(
            CONF_DEVICE_ID, entry.data.get(CONF_DEVICE_ID, 1)
        )
        self.host = entry.options.get(CONF_HOST, entry.data.get(CONF_HOST))
        self.port = entry.options.get(CONF_PORT, entry.data.get(CONF_PORT, 502))
        self.client = AsyncModbusTcpClient(host=self.host, port=self.port)

    async def async_setup(self):
        filename = self.entry.options.get(
            CONF_FILENAME, "samsung_mono_ehs_ht_quiet.yaml"
        )
        template_path = os.path.join(os.path.dirname(__file__), "templates", filename)
        self.device_template = DeviceTemplate(template_path)
        try:
            await self.device_template.load()
        except (OSError, ValueError, TypeError, KeyError) as err:
            _LOGGER.error("Cannot load device template %s: %s", template_path, err)
            raise ConfigEntryError(
                f"Cannot load device template {filename}: {err}"
            ) from err
        for sub_device in self.device_template.sub_devices:
            if sub_device.messageIdBindingRegisterOffset is not None:
                try:
                    sub_device.validate_fsv_capacity()
                except ValueError as err:
                    _LOGGER.warning("%s", err)
        try:
            if not await self.client.connect():
                raise ModbusException("Connection refused or timed out")
            for sub_device in self.device_template.sub_devices:
                if sub_device.messageIds:
                    await self.async_bind_message_ids(sub_device)
        except (ModbusException, OSError, HomeAssistantError) as err:
            raise ConfigEntryNotReady(
                f"Cannot initialize {self.host}:{self.port}, device {self.device_id}: {err}"
            ) from err

    async def async_close(self):
        """Wait for outstanding I/O before closing the connection."""
        async with self._io_lock:
            self.client.close()

    @staticmethod
    def _check_response(response, operation):
        if response is None or response.isError():
            raise HomeAssistantError(f"{operation}: Modbus error response {response}")

    async def _write_register(self, address, value, sub_device):
        """Write with the I/O lock already held; never mask a rejected write."""
        if type(value) is not int or not 0 <= value <= 65535:
            raise ServiceValidationError(
                f"Register value must be an integer from 0 to 65535; got {value!r}"
            )
        try:
            response = await self.client.write_register(
                address, value, device_id=self.device_id
            )
            self._check_response(response, f"Writing register {address}")
        except (ModbusException, OSError, HomeAssistantError) as err:
            _LOGGER.error(
                "Write failed for %s:%s device %s / %s, register %s, value %s: %s",
                self.host,
                self.port,
                self.device_id,
                sub_device.name,
                address,
                value,
                err,
            )
            raise HomeAssistantError(
                f"Failed to write register {address} for {sub_device.name}: {err}"
            ) from err

    def _apply_pending_write(self, address, value, sub_device, timeout):
        self.pending_writes[(sub_device, address)] = (time.monotonic() + timeout, value)
        if self.data and isinstance(self.data.get(sub_device), dict):
            data = {device: dict(registers) for device, registers in self.data.items()}
            data[sub_device][address] = value
            self.async_set_updated_data(data)

    async def async_write_register(
        self, address: int, value: int, sub_device, timeout: float
    ):
        async with self._io_lock:
            await self._write_register(address, value, sub_device)
            self._apply_pending_write(address, value, sub_device, timeout)

    async def async_bind_message_ids(self, sub_device, additional_ids=None):
        async with self._io_lock:
            return await self._bind_message_ids(sub_device, additional_ids)

    async def async_write_masked_register(
        self, address, value, mask, sub_device, timeout
    ):
        """Read/merge/write one field atomically, preserving pending changes."""
        if type(mask) is not int or not 1 <= mask <= 0xFFFF:
            raise ServiceValidationError("Mask must be an integer from 1 to 65535")
        shift = (mask & -mask).bit_length() - 1
        field_max = mask >> shift
        if field_max & (field_max + 1):
            raise ServiceValidationError("Writable masks must select contiguous bits")
        if type(value) is not int or not 0 <= value <= field_max:
            raise ServiceValidationError(
                f"Value {value!r} does not fit mask {mask:#06x}"
            )
        async with self._io_lock:
            pending = self.pending_writes.get((sub_device, address))
            now = time.monotonic()
            try:
                if pending is not None and pending[0] > now:
                    # Device readback may still contain the old value. Preserve
                    # the most recent accepted write, including the other field.
                    current = pending[1]
                    timeout = max(timeout, pending[0] - now)
                else:
                    response = await self.client.read_holding_registers(
                        address=address, count=1, device_id=self.device_id
                    )
                    self._check_response(
                        response, f"Reading register {address} before masked write"
                    )
                    registers = getattr(response, "registers", None)
                    if registers is None or len(registers) != 1:
                        raise HomeAssistantError(
                            f"Expected one register at {address} before masked write"
                        )
                    current = registers[0]
                if type(current) is not int or not 0 <= current <= 0xFFFF:
                    raise HomeAssistantError(
                        f"Invalid register value {current!r} at {address}"
                    )
                merged = (current & (0xFFFF ^ mask)) | (value << shift)
                await self._write_register(address, merged, sub_device)
                self._apply_pending_write(address, merged, sub_device, timeout)
            except (ModbusException, OSError, HomeAssistantError) as err:
                _LOGGER.error(
                    "Masked write failed for %s, device %s, register %s, mask %#06x, value %s: %s",
                    sub_device.name,
                    self.device_id,
                    address,
                    mask,
                    value,
                    err,
                )
                raise HomeAssistantError(
                    f"Failed to update field at register {address}: {err}"
                ) from err

    async def _bind_message_ids(self, sub_device, additional_ids=None):
        final_ids = sub_device.get_final_message_ids(additional_ids)
        try:
            sub_device.validate_binding_count(len(final_ids))
        except ValueError as err:
            _LOGGER.error("Message ID binding rejected: %s", err)
            raise ServiceValidationError(str(err)) from err
        base = sub_device.messageIdBindingRegisterOffset
        if base is None or sub_device.readMessageIdRegisterOffset is None:
            raise ServiceValidationError(
                f"No message ID binding offsets configured for {sub_device.name}"
            )
        if not final_ids or len(final_ids) > 123:
            raise ServiceValidationError(
                f"Invalid binding count {len(final_ids)} for {sub_device.name}; expected 1–123"
            )
        try:
            response = await self.client.write_registers(
                base, final_ids, device_id=self.device_id
            )
            self._check_response(response, f"Binding message IDs at register {base}")
        except (ModbusException, OSError, HomeAssistantError) as err:
            _LOGGER.error(
                "Binding failed for %s:%s device %s / %s at register %s: %s",
                self.host,
                self.port,
                self.device_id,
                sub_device.name,
                base,
                err,
            )
            raise HomeAssistantError(
                f"Failed to bind message IDs for {sub_device.name}: {err}"
            ) from err
        _LOGGER.debug(
            "Bound %s message IDs for %s at register %s",
            len(final_ids),
            sub_device.name,
            base,
        )
        return final_ids

    async def async_write_fsv(
        self, unit_name: str, message_id: int, value: int
    ) -> bool:
        return await self.async_write_fsvs(unit_name, [(message_id, value)])

    async def async_write_fsvs(self, unit_name, settings) -> bool:
        """Validate all settings first, then serialize the entire sequence."""
        sub_device = next(
            (
                sd
                for sd in self.device_template.sub_devices
                if sd.name.casefold() == unit_name.casefold()
            ),
            None,
        )
        if sub_device is None:
            raise ServiceValidationError(
                f"Target unit {unit_name!r} not found in template"
            )
        try:
            sub_device.validate_fsv_capacity()
        except ValueError as err:
            _LOGGER.error("FSV action rejected: %s", err)
            raise ServiceValidationError(str(err)) from err
        for message_id, value in settings:
            if type(value) is not int or not 0 <= value <= 65535:
                raise ServiceValidationError(
                    "FSV values must be unsigned 16-bit integers"
                )
            if type(message_id) is not int or not 0 <= message_id <= 65535:
                raise ServiceValidationError(
                    "FSV message IDs must be unsigned 16-bit integers"
                )
        # Reuse one temporary slot. Hold the lock across all settings so reads
        # and other actions cannot interleave with a partially written curve.
        async with self._io_lock:
            for index, (message_id, value) in enumerate(settings):
                try:
                    final_ids = await self._bind_message_ids(sub_device, [message_id])
                    address = sub_device.readMessageIdRegisterOffset + final_ids.index(
                        message_id
                    )
                    await asyncio.sleep(1.0)
                    await self._write_register(address, value, sub_device)
                    if message_id in sub_device.messageIds:
                        timeout = self.entry.options.get(CONF_SCAN_INTERVAL, 30)
                        self._apply_pending_write(address, value, sub_device, timeout)
                except HomeAssistantError as err:
                    raise HomeAssistantError(
                        f"FSV sequence stopped at message ID {message_id}: "
                        f"{index} of {len(settings)} writes accepted; earlier writes "
                        f"have not been rolled back. {err}"
                    ) from err
                _LOGGER.info(
                    "Modbus accepted FSV message ID %s, value %s for %s (register %s)",
                    message_id,
                    value,
                    sub_device.name,
                    address,
                )
        return True

    async def _async_update_data(self):
        async with self._io_lock:
            return await self._read_data()

    async def _read_data(self):
        device_data = {}
        for sub_device in self.device_template.sub_devices:
            if sub_device.min_address is None:
                continue
            try:
                started = time.monotonic()
                parsed_data = {}
                for address in range(
                    sub_device.min_address, sub_device.max_address + 1, 125
                ):
                    count = min(125, sub_device.max_address - address + 1)
                    response = await self.client.read_holding_registers(
                        address=address, count=count, device_id=self.device_id
                    )
                    self._check_response(
                        response, f"Reading registers {address}–{address + count - 1}"
                    )
                    registers = getattr(response, "registers", None)
                    if registers is None or len(registers) != count:
                        raise HomeAssistantError(
                            f"Incomplete response at register {address}: expected {count} registers, received {len(registers) if registers is not None else 0}"
                        )
                    parsed_data.update(enumerate(registers, start=address))
                now = time.monotonic()
                self.read_durations[sub_device.name] = now - started
                self.measured_interval[sub_device.name] = now - self.last_poll_time.get(
                    sub_device.name,
                    now - self.entry.options.get(CONF_SCAN_INTERVAL, 30),
                )
                self.last_poll_time[sub_device.name] = now
                for address, value in parsed_data.items():
                    key = (sub_device, address)
                    if key not in self.pending_writes:
                        continue
                    expires, pending_value = self.pending_writes[key]
                    if value == pending_value:
                        del self.pending_writes[key]
                    elif now < expires:
                        parsed_data[address] = pending_value
                    else:
                        del self.pending_writes[key]
                        _LOGGER.warning(
                            "Write not confirmed for %s register %s: requested %s, read back %s; displaying device value",
                            sub_device.name,
                            address,
                            pending_value,
                            value,
                        )
                device_data[sub_device] = parsed_data
                _LOGGER.debug(
                    "Read %s registers for %s in %.3fs",
                    len(parsed_data),
                    sub_device.name,
                    now - started,
                )
                await asyncio.sleep(0.1)
            except (ModbusException, OSError, HomeAssistantError) as err:
                # DataUpdateCoordinator logs failures and recovery without flooding logs.
                raise UpdateFailed(
                    f"Error reading {self.host}:{self.port}, device {self.device_id} / {sub_device.name}: {err}"
                ) from err
        return device_data
