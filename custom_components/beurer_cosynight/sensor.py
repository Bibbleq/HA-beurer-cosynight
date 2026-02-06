"""Platform for sensor entity integration."""
from __future__ import annotations

import logging

from . import beurer_cosynight
from .const import DOMAIN

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTime, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import CoordinatorEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    # Get coordinator and devices
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    
    if not devices:
        _LOGGER.warning("No devices found for Beurer CosyNight")
        return
    
    # Initialize entity storage for RefreshButton coordination
    entities_key = f"{config_entry.entry_id}_entities"
    hass.data[DOMAIN].setdefault(entities_key, {})
    
    entities = []
    for d in devices:
        device_timer = DeviceTimer(coordinator, d)
        last_updated = LastUpdatedSensor(coordinator, d)
        entities.append(device_timer)
        entities.append(last_updated)
        
        # Store sensor entity reference for RefreshButton
        hass.data[DOMAIN][entities_key].setdefault(d.id, []).extend([device_timer, last_updated])
    
    add_entities(entities)
    _LOGGER.info("Added %d sensor entities for Beurer CosyNight", len(entities))


class DeviceTimer(CoordinatorEntity, SensorEntity):
    """Sensor for the actual Beurer device timer (remaining time)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = "Remaining Time"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_device_timer"
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_available = True

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
        status = self.coordinator.data.get(self._device.id)
        if status is None:
            return 0
        return status.timer

    @property
    def state(self):
        """Return formatted time string."""
        status = self.coordinator.data.get(self._device.id)
        if status is None or status.timer == 0:
            return "Off"
        
        seconds = status.timer
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


class LastUpdatedSensor(CoordinatorEntity, SensorEntity):
    """Sensor for showing when the device status was last updated."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, device) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._attr_name = "Last Updated"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_last_updated"
        self._attr_available = True

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
        """Return the last updated timestamp."""
        # Return the current time when coordinator has data, or None if no successful update
        if self.coordinator.last_update_success:
            return dt_util.now()
        return None
