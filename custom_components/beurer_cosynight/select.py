"""Platform for select entity integration."""
from __future__ import annotations

import logging

from . import beurer_cosynight
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.select import (PLATFORM_SCHEMA, SelectEntity)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry

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
            entities.append(BodyZone(hub, d, hass))
            entities.append(FeetZone(hub, d, hass))
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
        entities.append(BodyZone(hub, d))
        entities.append(FeetZone(hub, d))
    add_entities(entities)


class _Zone(SelectEntity):

    def __init__(self, hub, device, name, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._name = f'{device.name} {name}'
        self._status = None

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


class BodyZone(_Zone):

    def __init__(self, hub, device, hass):
        super().__init__(hub, device, 'Body Zone', hass)

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
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=int(option),
            feetSetting=self._status.feetSetting,
            id=self._status.id,
            timespan=3600
        )
        await self._hass.async_add_executor_job(self._hub.quickstart, qs)


class FeetZone(_Zone):

    def __init__(self, hub, device, hass):
        super().__init__(hub, device, 'Feet Zone', hass)

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
        
        qs = beurer_cosynight.Quickstart(
            bodySetting=self._status.bodySetting,
            feetSetting=int(option),
            id=self._status.id,
            timespan=3600
        )
        await self._hass.async_add_executor_job(self._hub.quickstart, qs)
