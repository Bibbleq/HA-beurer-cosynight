"""Platform for select entity integration."""
from __future__ import annotations

import logging

from . import beurer_cosynight
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.select import (PLATFORM_SCHEMA, SelectEntity)
from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import UnitOfTime

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
        
        entities = []
        for d in devices:
            body_zone = BodyZone(hub, d, hass)
            feet_zone = FeetZone(hub, d, hass)
            duration_timer = _Timer(hub, d, hass)
            device_timer = DeviceTimer(hub, d, hass)
            stop_button = StopButton(hub, d, hass)
            
            # Link duration timer to zones
            body_zone._timer = duration_timer
            feet_zone._timer = duration_timer
            
            entities.append(body_zone)
            entities.append(feet_zone)
            entities.append(duration_timer)
            entities.append(device_timer)
            entities.append(stop_button)
        
        add_entities(entities)
        _LOGGER.info("Added %d entities for Beurer CosyNight", len(entities))
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


class StopButton(ButtonEntity):
    """Button to stop the massage session."""

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._name = f'{device.name} Stop'
        self._attr_unique_id = f"beurer_cosynight_{device.id}_stop_button"

    @property
    def name(self) -> str:
        return self._name

    async def async_press(self) -> None:
        """Stop the massage by setting both zones to 0."""
        try:
            # Get current status
            status = await self._hass.async_add_executor_job(
                self._hub.get_status, self._device.id
            )
            
            # Create quickstart with both zones set to 0
            qs = beurer_cosynight.Quickstart(
                bodySetting=0,
                feetSetting=0,
                id=status.id,
                timespan=0
            )
            
            # Send to device
            await self._hass.async_add_executor_job(self._hub.quickstart, qs)
            _LOGGER.debug("Stopped massage session for %s", self._device.name)
        except Exception as e:
            _LOGGER.error("Failed to stop massage: %s", e)


class DeviceTimer(SensorEntity):
    """Sensor for the actual Beurer device timer (remaining time)."""

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._name = f'{device.name} Timer'
        self._attr_unique_id = f"beurer_cosynight_{device.id}_device_timer"
        self._status = None
        self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        self._attr_device_class = SensorDeviceClass.DURATION

    @property
    def name(self) -> str:
        return self._name

    @property
    def native_value(self):
        """Return the remaining time in seconds from the device."""
        if self._status is None:
            return 0
        return self._status.timer

    async def async_update(self) -> None:
        """Update the entity (async)."""
        self._status = await self._hass.async_add_executor_job(
            self._hub.get_status, self._device.id
        )

    def update(self) -> None:
        """Synchronous update - no-op."""
        pass


class _Zone(SelectEntity):

    def __init__(self, hub, device, name, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._name = f'{device.name} {name}'
        self._status = None
        self._attr_unique_id = f"beurer_cosynight_{device.id}_{name.lower().replace(' ', '_')}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def options(self):
        return [str(x) for x in range(0, 10)]

    async def async_update(self) -> None:
        """Update the entity (async)."""
        self._status = await self._hass.async_add_executor_job(
            self._hub.get_status, self._device.id
        )

    def update(self) -> None:
        """Synchronous update - no-op for now."""
        # This is called by Home Assistant, but we use async_update instead
        pass


class _Timer(SelectEntity):
    """Timer duration selector."""

    # Duration options in seconds
    DURATION_OPTIONS = {
        "30 min": 1800,
        "1 hour": 3600,
        "2 hours": 7200,
        "3 hours": 10800,
        "4 hours": 14400,
    }

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._name = f'{device.name} Timer'
        self._attr_unique_id = f"beurer_cosynight_{device.id}_timer"
        self._current_duration = "1 hour"  # Default

    @property
    def name(self) -> str:
        return self._name

    @property
    def current_option(self) -> str:
        return self._current_duration

    @property
    def options(self) -> list[str]:
        return list(self.DURATION_OPTIONS.keys())

    async def async_select_option(self, option: str) -> None:
        """Set the duration option."""
        self._current_duration = option

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
        
        # Get duration from timer entity if available
        timespan = 3600  # default 1 hour
        if self._timer:
            duration_label = self._timer.current_option
            timespan = _Timer.DURATION_OPTIONS.get(duration_label, 3600)
        
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
        
        # Get duration from timer entity if available
        timespan = 3600  # default 1 hour
        if self._timer:
            duration_label = self._timer.current_option
            timespan = _Timer.DURATION_OPTIONS.get(duration_label, 3600)
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=self._status.bodySetting,
            feetSetting=int(option),
            id=self._status.id,
            timespan=timespan
        )
        await self._hass.async_add_executor_job(self._hub.quickstart, qs)
