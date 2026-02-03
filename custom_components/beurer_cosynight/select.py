"""Platform for select entity integration."""
from __future__ import annotations

import logging

from . import beurer_cosynight
from .const import DOMAIN
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.select import (PLATFORM_SCHEMA, SelectEntity)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

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
            body_zone = BodyZone(hub, d, hass, config_entry.entry_id)
            feet_zone = FeetZone(hub, d, hass, config_entry.entry_id)
            
            entities.append(body_zone)
            entities.append(feet_zone)
            
            # Store entity references for RefreshButton
            hass.data[DOMAIN][entities_key].setdefault(d.id, []).extend([body_zone, feet_zone])
        
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

    def __init__(self, hub, device, name, hass, config_entry_id=None) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._attr_name = name
        self._status = None
        self._attr_unique_id = f"beurer_cosynight_{device.id}_{name.lower().replace(' ', '_')}"
        self._attr_extra_state_attributes = {}
        self._config_entry_id = config_entry_id
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
    def options(self):
        return [str(x) for x in range(0, 10)]

    def _get_timer_value(self) -> float:
        """Get timer value from the number entity if available."""
        default_timer = 1.0  # Default 1 hour

        if self._config_entry_id:
            entities_key = f"{self._config_entry_id}_entities"
            device_entities = self._hass.data.get(DOMAIN, {}).get(entities_key, {}).get(self._device.id, [])
            for entity in device_entities:
                # Look for the DurationTimer entity by checking unique_id
                if hasattr(entity, '_attr_unique_id') and '_timer' in entity._attr_unique_id:
                    value = entity.native_value
                    # Ensure we have a valid numeric timer value (must be positive)
                    if isinstance(value, (int, float)) and value > 0:
                        return float(value)
                    # If timer value is invalid, use default
                    _LOGGER.warning(
                        "Timer value %s is invalid for device %s, using default of %s hours",
                        value, self._device.id, default_timer
                    )
                    return default_timer
        return default_timer

    async def async_update(self) -> None:
        """Update the entity (async)."""
        try:
            self._status = await self._hass.async_add_executor_job(
                self._hub.get_status, self._device.id
            )
            # Update last_updated timestamp
            self._attr_extra_state_attributes["last_updated"] = dt_util.now().isoformat()
            self._attr_available = True
        except beurer_cosynight.BeurerCosyNight.AuthenticationError as e:
            _LOGGER.error(
                "Authentication failed for %s: %s. Please reconfigure the integration.",
                self._device.name, e
            )
            self._attr_available = False
        except Exception as e:
            _LOGGER.error("Failed to update zone for %s: %s", self._device.name, e)

    def update(self) -> None:
        """Synchronous update - no-op for now."""
        # This is called by Home Assistant, but we use async_update instead
        pass


class BodyZone(_Zone):

    def __init__(self, hub, device, hass, config_entry_id=None):
        super().__init__(hub, device, 'Body Zone', hass, config_entry_id)

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
        timer_hours = self._get_timer_value()
        timespan = int(timer_hours * 3600)  # Convert hours to seconds
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=int(option),
            feetSetting=self._status.feetSetting,
            id=self._status.id,
            timespan=timespan
        )
        try:
            await self._hass.async_add_executor_job(self._hub.quickstart, qs)
        except beurer_cosynight.BeurerCosyNight.AuthenticationError as e:
            _LOGGER.error(
                "Authentication failed for %s: %s. Please reconfigure the integration.",
                self._device.name, e
            )
            self._attr_available = False
            raise


class FeetZone(_Zone):

    def __init__(self, hub, device, hass, config_entry_id=None):
        super().__init__(hub, device, 'Feet Zone', hass, config_entry_id)

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
        timer_hours = self._get_timer_value()
        timespan = int(timer_hours * 3600)  # Convert hours to seconds
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=self._status.bodySetting,
            feetSetting=int(option),
            id=self._status.id,
            timespan=timespan
        )
        try:
            await self._hass.async_add_executor_job(self._hub.quickstart, qs)
        except beurer_cosynight.BeurerCosyNight.AuthenticationError as e:
            _LOGGER.error(
                "Authentication failed for %s: %s. Please reconfigure the integration.",
                self._device.name, e
            )
            self._attr_available = False
            raise
