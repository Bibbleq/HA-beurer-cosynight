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

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
})


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
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

    def __init__(self, hub, device, name) -> None:
        self._hub = hub
        self._device = device
        self._name = f'{device.name} {name}'
        self._status = None
        self.update()

    @property
    def name(self) -> str:
        return self._name

    @property
    def options(self):
        return [str(x) for x in range(0, 10)]

    def update(self) -> None:
        self._status = self._hub.get_status(self._device.id)


class BodyZone(_Zone):

    def __init__(self, hub, device):
        super().__init__(hub, device, 'Body Zone')

    @property
    def current_option(self):
        return str(self._status.bodySetting)

    def select_option(self, option: str) -> None:
        self.update()
        qs = beurer_cosynight.Quickstart(bodySetting=int(option),
                                         feetSetting=self._status.feetSetting,
                                         id=self._status.id,
                                         timespan=3600)
        self._hub.quickstart(qs)


class FeetZone(_Zone):

    def __init__(self, hub, device):
        super().__init__(hub, device, 'Feet Zone')

    @property
    def current_option(self):
        return str(self._status.feetSetting)

    def select_option(self, option: str) -> None:
        self.update()
        qs = beurer_cosynight.Quickstart(bodySetting=self._status.bodySetting,
                                         feetSetting=int(option),
                                         id=self._status.id,
                                         timespan=3600)
        self._hub.quickstart(qs)
