import logging
import os
import time
from datetime import timedelta
import asyncio
from pymodbus.client import AsyncModbusTcpClient

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_DEVICE_ID, CONF_SCAN_INTERVAL, CONF_FILENAME

from .const import DOMAIN
from .device_template import DeviceTemplate

_LOGGER = logging.getLogger(__name__)

class SamsungModbusCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, 30))
        )
        self.entry = entry
        self.always_update = False
        
        self.last_poll_time = {}
        self.measured_interval = {}
        self.read_durations = {} 
        self.pending_writes = {}
        
        self.device_id = entry.data.get(CONF_DEVICE_ID)
        
        self.client = AsyncModbusTcpClient(
            host=entry.data.get(CONF_HOST),
            port=entry.data.get(CONF_PORT),
        )
        
    async def async_setup(self):
        await self.client.connect()
        
        template_filename = self.entry.options.get(CONF_FILENAME)
        template_path = os.path.join(os.path.dirname(__file__), "templates")
        template_file_path = os.path.join(template_path, template_filename)
        
        if not os.path.isfile(template_file_path):
            _LOGGER.error(f"Device template file {template_filename} not found in {template_path}.")
            return
            
        self.device_template = DeviceTemplate(template_file_path)
        await self.device_template.load()
        
        for sub_device in self.device_template.sub_devices:
            if len(sub_device.messageIds) > 0:
                await self.async_bind_message_ids(sub_device)
                
    async def async_write_register(self, address: int, value: int, sub_device, timeout: float):
        await self.client.write_register(address, value)
        
        expiration_time = time.time() + timeout
        self.pending_writes[address] = (expiration_time, value)
        
        if self.data and isinstance(self.data.get(sub_device), dict):
            self.data[sub_device][address] = value
            
    async def async_bind_message_ids(self, sub_device, additional_ids: list[int] = None) -> list[int]:        
        final_ids = sub_device.get_final_message_ids(additional_ids)

        binding_base = sub_device.messageIdBindingRegisterOffset
        
        try:
            await self.client.write_registers(binding_base, final_ids)
            _LOGGER.debug(f"Bound {len(final_ids)} message IDs to {sub_device.name} at {binding_base}.")
            return final_ids
        except Exception as e:
            _LOGGER.error(f"Failed to bind message IDs for {sub_device.name}: {e}")
            return []
        
    async def async_write_fsv(self, unit_name: str, message_id: int, value: int) -> bool:        
        target_sub_device = next((sd for sd in self.device_template.sub_devices if sd.name.lower() == unit_name.lower()), None)
        
        if not target_sub_device:
            _LOGGER.error(f"Target Unit '{unit_name}' not found in template.")
            return False

        final_ids = await self.async_bind_message_ids(target_sub_device, additional_ids=[message_id])
        if not final_ids or len(final_ids) == 0:
            return False

        data_base = target_sub_device.readMessageIdRegisterOffset
        slot_index = final_ids.index(message_id)
        target_data_register = data_base + slot_index

        try:
            await asyncio.sleep(1.0)
            await self.client.write_register(target_data_register, value)
            _LOGGER.info(f"Successfully wrote {value} to FSV message ID {message_id} (Reg {target_data_register}).")
            return True

        except Exception as e:
            _LOGGER.error(f"Failed to write FSV message ID {message_id}: {e}")
            return False

    async def _async_update_data(self):
        device_data = {}
        
        for sub_device in self.device_template.sub_devices:
            if not hasattr(sub_device, "min_address"):
                continue

            try:
                read_start = time.time()
                
                sub_device_data = await self.client.read_holding_registers(
                    address=sub_device.min_address,
                    count=sub_device.max_address - sub_device.min_address + 1,
                    device_id=self.device_id
                )
                _LOGGER.debug(f"Read {len(sub_device_data.registers) if sub_device_data.registers else 0} registers for {sub_device.name} (addresses {sub_device.min_address} to {sub_device.max_address})")
                
                read_end = time.time()
                self.read_durations[sub_device.name] = read_end - read_start
                
                if sub_device_data.isError():
                    raise UpdateFailed(f"Modbus Error reading {sub_device.name}: {sub_device_data}")
                
                now = time.time()
                if sub_device.name in self.last_poll_time:
                    self.measured_interval[sub_device.name] = now - self.last_poll_time[sub_device.name]
                else:
                    self.measured_interval[sub_device.name] = self.entry.options.get(CONF_SCAN_INTERVAL, 30)
                
                self.last_poll_time[sub_device.name] = now
                
                # Convert Modbus response to dictionary of {address: value}
                parsed_data = {}
                if hasattr(sub_device_data, "registers") and sub_device_data.registers:
                    for i, val in enumerate(sub_device_data.registers):
                        address = sub_device.min_address + i
                        
                        if address in self.pending_writes:
                            expiration_time, pending_val = self.pending_writes[address]
                            if now < expiration_time:
                                if val != pending_val:
                                    val = pending_val
                                else:
                                    del self.pending_writes[address]
                            else:
                                del self.pending_writes[address]
                                
                        parsed_data[address] = val
                        
                device_data[sub_device] = parsed_data
                
                await asyncio.sleep(0.1)
                
            except Exception as err:
                raise UpdateFailed(f"Error fetching data for {sub_device.name}: {err}") from err
                
        return device_data
