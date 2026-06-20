import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_DEVICE_ID, 
    CONF_SCAN_INTERVAL, 
    CONF_FILENAME
)

from .const import DOMAIN

class SamsungModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Tell Home Assistant to use our custom Options Flow Handler."""
        return SamsungModbusOptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"Samsung Heatpump ({user_input[CONF_HOST]})",
                data={
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_DEVICE_ID: user_input[CONF_DEVICE_ID],
                },
                options={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_FILENAME: user_input[CONF_FILENAME],
                }
            )

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=502): int,
            vol.Required(CONF_DEVICE_ID, default=1): int,
            vol.Required(CONF_SCAN_INTERVAL, default=30): int,
            vol.Required(CONF_FILENAME, default="samsung_mono_ehs_ht_quiet.yaml"): str,
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors
        )


class SamsungModbusOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle the Options flow when a user clicks 'Configure'."""


    async def async_step_init(self, user_input=None):
        """Manage the options UI."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_host = self.config_entry.data.get(CONF_HOST, "")
        current_port = self.config_entry.data.get(CONF_PORT, 502)
        current_device_id = self.config_entry.data.get(CONF_DEVICE_ID, 1)
        current_interval = self.config_entry.options.get(CONF_SCAN_INTERVAL, 30)
        current_filename = self.config_entry.options.get(CONF_FILENAME, "samsung_mono_ehs_ht_quiet.yaml")

        options_schema = vol.Schema({
            vol.Required(CONF_HOST, default=current_host): str,
            vol.Required(CONF_PORT, default=current_port): int,
            vol.Required(CONF_DEVICE_ID, default=current_device_id): int,
            vol.Required(CONF_SCAN_INTERVAL, default=current_interval): int,
            vol.Required(CONF_FILENAME, default=current_filename): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema
        )
