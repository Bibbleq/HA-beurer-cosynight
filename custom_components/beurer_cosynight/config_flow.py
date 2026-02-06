"""Config flow for Beurer CosyNight integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

from . import beurer_cosynight
from .const import (
    DOMAIN,
    CONF_PEAK_HOURS_START,
    CONF_PEAK_HOURS_END,
    CONF_OFFPEAK_INTERVAL_MINUTES,
    CONF_PEAK_INTERVAL_MINUTES,
    CONF_ACTIVE_BLANKET_ENABLED,
    DEFAULT_PEAK_HOURS_START,
    DEFAULT_PEAK_HOURS_END,
    DEFAULT_OFFPEAK_INTERVAL_MINUTES,
    DEFAULT_PEAK_INTERVAL_MINUTES,
    DEFAULT_ACTIVE_BLANKET_ENABLED,
)

_LOGGER = logging.getLogger(__name__)


class BeurerCosyNightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Beurer CosyNight."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

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
            except beurer_cosynight.BeurerCosyNight.AuthenticationError:
                _LOGGER.error("Authentication failed: invalid credentials")
                errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.error("Authentication failed: %s", e)
                errors["base"] = "cannot_connect"

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

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        """Handle reconfiguration of credentials."""
        errors = {}
        reconfigure_entry = self._get_reconfigure_entry()

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
                
                # Update the existing entry with new credentials
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data={**reconfigure_entry.data, **user_input},
                    title=username,
                )
            except beurer_cosynight.BeurerCosyNight.AuthenticationError:
                _LOGGER.error("Reconfiguration failed: invalid credentials")
                errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.error("Reconfiguration failed: %s", e)
                errors["base"] = "cannot_connect"

        # Pre-fill the username from existing config
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME, 
                    default=reconfigure_entry.data.get(CONF_USERNAME, "")
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "error_details": "Update your username and password"
            }
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Beurer CosyNight integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the polling options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current options or use defaults
        current_options = self._config_entry.options
        
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PEAK_HOURS_START,
                    default=current_options.get(
                        CONF_PEAK_HOURS_START, DEFAULT_PEAK_HOURS_START
                    ),
                ): str,
                vol.Optional(
                    CONF_PEAK_HOURS_END,
                    default=current_options.get(
                        CONF_PEAK_HOURS_END, DEFAULT_PEAK_HOURS_END
                    ),
                ): str,
                vol.Optional(
                    CONF_OFFPEAK_INTERVAL_MINUTES,
                    default=current_options.get(
                        CONF_OFFPEAK_INTERVAL_MINUTES, DEFAULT_OFFPEAK_INTERVAL_MINUTES
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_PEAK_INTERVAL_MINUTES,
                    default=current_options.get(
                        CONF_PEAK_INTERVAL_MINUTES, DEFAULT_PEAK_INTERVAL_MINUTES
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_ACTIVE_BLANKET_ENABLED,
                    default=current_options.get(
                        CONF_ACTIVE_BLANKET_ENABLED, DEFAULT_ACTIVE_BLANKET_ENABLED
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            description_placeholders={
                "peak_hours_start": "Time when peak hours start (HH:MM format, e.g., 20:00)",
                "peak_hours_end": "Time when peak hours end (HH:MM format, e.g., 08:00)",
                "offpeak_interval": "Update interval during off-peak hours (minutes)",
                "peak_interval": "Update interval during peak hours (minutes)",
                "active_enabled": "Enable aggressive polling when blanket is active",
            },
        )