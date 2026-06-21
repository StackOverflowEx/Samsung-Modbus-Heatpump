import logging
import json
import os
import aiofiles
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import SamsungModbusCoordinator

_LOGGER = logging.getLogger(__name__)

async def load_fsv_mapping():
    """Load the flat FSV mapping from the JSON file."""
    mapping_file = os.path.join(os.path.dirname(__file__), "fsv_mapping.json")
    try:
        async with aiofiles.open(mapping_file, mode='r', encoding='utf-8') as f:
            return json.loads(await f.read())
    except FileNotFoundError:
        _LOGGER.error(f"FSV mapping file not found at {mapping_file}. Make sure fsv_mapping.json exists.")
        return {}
    except json.JSONDecodeError as e:
        _LOGGER.error(f"Invalid JSON in fsv_mapping.json: {e}")
        return {}
    except Exception as e:
        _LOGGER.error(f"Unexpected error loading FSV mapping file: {e}")
        return {}

async def async_setup_services(hass: HomeAssistant, coordinator: SamsungModbusCoordinator):    
    fsv_mapping = await load_fsv_mapping()

    async def handle_set_fsv(call: ServiceCall):
        """Handle the UI call to set a Field Setting Value."""
        unit_name = str(call.data.get("unit_name"))
        fsv_code = str(call.data.get("fsv_code"))
        value = int(call.data.get("value"))

        if fsv_code not in fsv_mapping:
            _LOGGER.error(f"FSV Code '{fsv_code}' not found in fsv_mapping.json.")
            return

        target_message_id = fsv_mapping[fsv_code]

        success = await coordinator.async_write_fsv(unit_name, target_message_id, value)
        
        if success:
            _LOGGER.debug(f"Service call completed successfully for FSV {fsv_code}.")
        else:
            _LOGGER.error(f"Service call failed for FSV {fsv_code}.")

    hass.services.async_register(DOMAIN, "set_field_setting_value", handle_set_fsv)
