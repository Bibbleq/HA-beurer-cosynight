"""Platform for select entity integration."""
from __future__ import annotations

import logging
from datetime import datetime

from . import beurer_cosynight
from .const import DOMAIN
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.select import (PLATFORM_SCHEMA, SelectEntity)
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
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
            body_zone = BodyZone(hub, d, hass)
            feet_zone = FeetZone(hub, d, hass)
            duration_timer = _Timer(hub, d, hass)
            
            # Link duration timer to zones
            body_zone._timer = duration_timer
            feet_zone._timer = duration_timer
            
            entities.append(body_zone)
            entities.append(feet_zone)
            entities.append(duration_timer)
            
            # Store entity references for RefreshButton
            hass.data[DOMAIN][entities_key].setdefault(d.id, []).extend([body_zone, feet_zone, duration_timer])
        
        add_entities(entities)
        _LOGGER.info("Added %d select entities for Beurer CosyNight", len(entities))
    except Exception as e:
        _LOGGER.error("Failed to list devices from Beurer CosyNight: %s", e)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the select platform (for YAML config)."""
    username = config[CONF_USERNAME]
    password = config.get(CONF_PASSWORD)
    hub = beurer_cosynight.BeurerCosyNight()

    try:
        hub.authenticate(username, password)
    except Exception as e:
        _LOGGER.error("Could not connect to Beurer CosyNight hub: %s", e)
        return

    entities = []
    for d in hub.list_devices():
        entities.append(BodyZone(hub, d, hass))
        entities.append(FeetZone(hub, d, hass))
    add_entities(entities)


class _Zone(SelectEntity):

    _attr_has_entity_name = True

    def __init__(self, hub, device, name, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._attr_name = name
        self._status = None
        self._attr_unique_id = f"beurer_cosynight_{device.id}_{name.lower().replace(' ', '_')}"
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
    def options(self):
        return [str(x) for x in range(0, 10)]

    async def async_update(self) -> None:
        """Update the entity (async)."""
        self._status = await self._hass.async_add_executor_job(
            self._hub.get_status, self._device.id
        )
        # Update last_updated timestamp
        self._attr_extra_state_attributes["last_updated"] = datetime.now().isoformat()

    def update(self) -> None:
        """Synchronous update - no-op for now."""
        # This is called by Home Assistant, but we use async_update instead
        pass


class _Timer(NumberEntity):
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


class BodyZone(_Zone):

    def __init__(self, hub, device, hass):
        super().__init__(hub, device, 'Body Zone', hass)
        self._timer = None  # Will be set by async_setup_entry

    @property
    def current_option(self):
        if self._status is None:
            return "0"
        return str(self._status.bodySetting)

    async def async_select_option(self, option: str) -> None:
        """Update the body zone setting."""
        await self.async_update()
        if self._status is None:
            return
        
        # Get duration from timer entity if available (timer is now in hours)
        timespan = 3600  # default 1 hour
        if self._timer:
            timer_hours = self._timer.native_value
            timespan = int(timer_hours * 3600)  # Convert hours to seconds
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=int(option),
            feetSetting=self._status.feetSetting,
            id=self._status.id,
            timespan=timespan
        )
        await self._hass.async_add_executor_job(self._hub.quickstart, qs)


class FeetZone(_Zone):

    def __init__(self, hub, device, hass):
        super().__init__(hub, device, 'Feet Zone', hass)
        self._timer = None  # Will be set by async_setup_entry

    @property
    def current_option(self):
        if self._status is None:
            return "0"
        return str(self._status.feetSetting)

    async def async_select_option(self, option: str) -> None:
        """Update the feet zone setting."""
        await self.async_update()
        if self._status is None:
            return
        
        # Get duration from timer entity if available (timer is now in hours)
        timespan = 3600  # default 1 hour
        if self._timer:
            timer_hours = self._timer.native_value
            timespan = int(timer_hours * 3600)  # Convert hours to seconds
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=self._status.bodySetting,
            feetSetting=int(option),
            id=self._status.id,
            timespan=timespan
        )
        await self._hass.async_add_executor_job(self._hub.quickstart, qs)
