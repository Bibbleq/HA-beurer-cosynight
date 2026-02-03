"""Platform for button entity integration."""
from __future__ import annotations

import logging

from . import beurer_cosynight
from .const import DOMAIN

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from a config entry."""
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
            stop_button = StopButton(hub, d, hass)
            refresh_button = RefreshButton(hub, d, hass, config_entry)
            
            entities.append(stop_button)
            entities.append(refresh_button)
        
        add_entities(entities)
        _LOGGER.info("Added %d button entities for Beurer CosyNight", len(entities))
    except Exception as e:
        _LOGGER.error("Failed to list devices from Beurer CosyNight: %s", e)


class StopButton(ButtonEntity):
    """Button to stop the massage session."""

    _attr_has_entity_name = True

    def __init__(self, hub, device, hass) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._attr_name = "Stop"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_stop_button"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Beurer",
            model="CosyNight",
        )

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


class RefreshButton(ButtonEntity):
    """Button to force refresh all entities for this device."""

    _attr_has_entity_name = True

    def __init__(self, hub, device, hass, config_entry) -> None:
        self._hub = hub
        self._hass = hass
        self._device = device
        self._config_entry = config_entry
        self._attr_name = "Refresh"
        self._attr_unique_id = f"beurer_cosynight_{device.id}_refresh_button"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link this entity to a device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Beurer",
            model="CosyNight",
        )

    async def async_press(self) -> None:
        """Force refresh all entities for this device."""
        try:
            # Get all entities stored for this device
            device_data = self._hass.data.get(DOMAIN, {}).get(f"{self._config_entry.entry_id}_entities", {})
            entities = device_data.get(self._device.id, [])
            
            if not entities:
                _LOGGER.debug("No entities found to refresh for device %s", self._device.name)
                return
            
            # Trigger update for all entities
            for entity in entities:
                await entity.async_update_ha_state(force_refresh=True)
            
            _LOGGER.debug("Refreshed %d entities for device %s", len(entities), self._device.name)
        except Exception as e:
            _LOGGER.error("Failed to refresh entities: %s", e)
