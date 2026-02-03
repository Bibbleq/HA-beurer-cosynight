"""Platform for number entity integration."""
from __future__ import annotations

import logging
from datetime import datetime

from . import beurer_cosynight
from .const import DOMAIN

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities from a config entry."""
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    
    # Use Home Assistant's config directory for token storage
    token_path = hass.config.path(f'.beurer_cosynight_token_{config_entry.entry_id}')
    
    def create_and_auth():
        hub = beurer_cosynight.BeurerCosyNight(token_path=token_path)
        hub.authenticate(username, password)
        return hub
    
    try:
        hub = await hass.async_add_executor_job(create_and_auth)
    except Exception as e:
        _LOGGER.error("Could not authenticate to Beurer CosyNight hub: %s", e)
        return
    
    def list_devs():
        return hub.list_devices()
    
    try:
        devices = await hass.async_add_executor_job(list_devs)
        if not devices:
            _LOGGER.warning("No devices found for Beurer CosyNight")
            return
        
        # Initialize entity storage for coordination
        entities_key = f"{config_entry.entry_id}_entities"
        hass.data[DOMAIN].setdefault(entities_key, {})
        
        entities = []
        for d in devices:
            duration_timer = DurationTimer(hub, d, hass)
            entities.append(duration_timer)
            
            # Store entity reference for coordination with other entities
            hass.data[DOMAIN][entities_key].setdefault(d.id, []).append(duration_timer)
        
        add_entities(entities)
        _LOGGER.info("Added %d number entities for Beurer CosyNight", len(entities))
    except Exception as e:
        _LOGGER.error("Failed to list devices from Beurer CosyNight: %s", e)


class DurationTimer(NumberEntity):
    """Timer duration number entity (slider in hours)."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0.5
    _attr_native_max_value = 12.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._attr_name = "Duration"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_timer"
        self._attr_native_value = 1.0  # Default 1 hour
        self._attr_extra_state_attributes = {"last_updated": datetime.now().isoformat()}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Beurer",
            model="CosyNight",
        )

    @property
    def native_value(self) -> float:
        """Return the current timer value in hours."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set the timer duration and apply it immediately to both zones."""
        self._attr_native_value = value
        
        # Convert hours to seconds
        timespan = int(value * 3600)
        
        # Get current device status
        try:
            status = await self._hass.async_add_executor_job(
                self._hub.get_status, self._device.id
            )
            
            # Create quickstart command with current zone values and new timer
            qs = beurer_cosynight.Quickstart(
                bodySetting=status.bodySetting,
                feetSetting=status.feetSetting,
                id=status.id,
                timespan=timespan
            )
            
            # Send the quickstart command
            await self._hass.async_add_executor_job(self._hub.quickstart, qs)
            
            # Update last_updated timestamp
            self._attr_extra_state_attributes["last_updated"] = datetime.now().isoformat()
            
            _LOGGER.info(
                "Timer set to %.1f hours (%d seconds) and applied to device %s",
                value, timespan, self._device.name
            )
        except Exception as e:
            _LOGGER.error("Failed to apply timer change: %s", e)
            raise

    def update(self) -> None:
        """Update - no-op for timer."""
        pass
