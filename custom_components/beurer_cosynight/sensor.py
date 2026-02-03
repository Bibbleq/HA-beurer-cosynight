"""Platform for sensor entity integration."""
from __future__ import annotations

import logging
from datetime import datetime

from . import beurer_cosynight
from .const import DOMAIN

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTime, CONF_PASSWORD, CONF_USERNAME
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
    """Set up sensor entities from a config entry."""
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
        
        # Initialize entity storage for RefreshButton coordination
        entities_key = f"{config_entry.entry_id}_entities"
        hass.data[DOMAIN].setdefault(entities_key, {})
        
        entities = []
        for d in devices:
            device_timer = DeviceTimer(hub, d, hass)
            entities.append(device_timer)
            
            # Store sensor entity reference for RefreshButton
            hass.data[DOMAIN][entities_key].setdefault(d.id, []).append(device_timer)
        
        add_entities(entities)
        _LOGGER.info("Added %d sensor entities for Beurer CosyNight", len(entities))
    except Exception as e:
        _LOGGER.error("Failed to list devices from Beurer CosyNight: %s", e)


class DeviceTimer(SensorEntity):
    """Sensor for the actual Beurer device timer (remaining time)."""

    _attr_has_entity_name = True
    _attr_should_poll = True  # Enable automatic polling

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._attr_name = "Remaining Time"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_device_timer"
        self._status = None
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_extra_state_attributes = {}

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
    def native_value(self):
        """Return the remaining time in seconds from the device."""
        if self._status is None:
            return 0
        return self._status.timer

    @property
    def state(self):
        """Return formatted time string."""
        if self._status is None or self._status.timer == 0:
            return "Off"
        
        seconds = self._status.timer
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    async def async_update(self) -> None:
        """Update the entity (async)."""
        try:
            self._status = await self._hass.async_add_executor_job(
                self._hub.get_status, self._device.id
            )
            # Update last_updated timestamp
            self._attr_extra_state_attributes["last_updated"] = datetime.now().isoformat()
        except Exception as e:
            _LOGGER.error("Failed to update device timer for %s: %s", self._device.name, e)

    def update(self) -> None:
        """Synchronous update - no-op."""
        pass
