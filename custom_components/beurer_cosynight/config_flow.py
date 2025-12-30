"""Config flow for Beurer CosyNight integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from . import beurer_cosynight
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BeurerCosyNightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beurer CosyNight."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            # Validate credentials (run in executor to avoid blocking)
            def create_and_authenticate():
                hub = beurer_cosynight.BeurerCosyNight()
                hub.authenticate(username, password)
                return hub

            try:
                await self.hass.async_add_executor_job(create_and_authenticate)
                return self.async_create_entry(title=username, data=user_input)
            except Exception as e:
                _LOGGER.error("Authentication failed: %s", e)
                errors["base"] = "invalid_auth"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user", 
            data_schema=data_schema, 
            errors=errors,
            description_placeholders={
                "error_details": "Check username and password"
            }
        )