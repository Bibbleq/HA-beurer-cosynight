"""Beurer CosyNight integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from . import beurer_cosynight
from .coordinator import BeurerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["select", "button", "sensor", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    token_path = hass.config.path(f'.beurer_cosynight_token_{entry.entry_id}')
    
    def create_hub():
        hub = beurer_cosynight.BeurerCosyNight(
            token_path=token_path,
            username=username,
            password=password
        )
        hub.authenticate(username, password)
        return hub
    
    try:
        hub = await hass.async_add_executor_job(create_hub)
    except Exception as e:
        _LOGGER.error("Authentication failed: %s", e)
        return False
    
    # Get list of devices
    def list_devices():
        return hub.list_devices()
    
    try:
        devices = await hass.async_add_executor_job(list_devices)
    except Exception as e:
        _LOGGER.error("Failed to list devices: %s", e)
        return False
    
    # Create coordinator
    coordinator = BeurerCoordinator(hass, hub, devices, entry)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store shared hub instance and coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
        "coordinator": coordinator,
        "devices": devices,
    }
    
    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORMS
    )
    
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok

