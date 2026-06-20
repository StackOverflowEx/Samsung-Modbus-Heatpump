import aiofiles
import yaml
import logging

_LOGGER = logging.getLogger(__name__)

class DeviceTemplate:
    
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def load(self):
        self.definition = await self.read_yaml()
        self.device_name = self.definition.get("name", "Unknown Device")
        self.sub_devices = [SubDeviceTemplate(sub_def) for sub_def in self.definition.get("devices", [])]

    async def read_yaml(self):
        async with aiofiles.open(self.file_path, mode='r') as f:
            content = await f.read()
            return yaml.safe_load(content)

class SubDeviceTemplate:
    
    def __init__(self, definition: dict):
        self.definition = definition
        self.process_definition()
        
    def process_definition(self):
        self.name = self.definition.get("name", "Unknown SubDevice")
        self.model = self.definition.get("model", "Unknown Model")
        self.capacity = self.definition.get("capacity", "Unknown Capacity")
        self.capacity_unit = self.definition.get("capacity_unit", None)
        self.messageIdBindingRegisterOffset = self.definition.get("bindMessageIdRegisterOffset", None)
                
        self.messageIds = []
        register = self.definition.get("readMessageIdRegisterOffset", None)
        for register_def in self.definition.get("registers", []):
            if register is None or self.messageIdBindingRegisterOffset is None:
                logging.warning(f"SubDevice {self.name} has register definitions but no readMessageIdRegisterOffset or bindMessageIdRegisterOffset defined. Skipping messageId binding.")
                break
            
            if "messageId" in register_def:
                if "address" in register_def:
                    logging.warning(f"SubDevice {self.name} register definition has both 'address' and 'messageId' defined. 'address' will be ignored.")
                register_def["address"] = register
                self.messageIds.append(register_def["messageId"])
                register += 1
                
        #Get min and max address values
        addresses = [reg.get("address") for reg in self.definition.get("registers", []) if "address" in reg]
        if addresses:
            self.min_address = min(addresses)
            self.max_address = max(addresses)
