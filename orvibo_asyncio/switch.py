"""
Support for Orvibo S20 Wifi Smart Switches.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/switch.orvibo/
"""
import logging

import voluptuous as vol

from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA, DOMAIN)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_MAC, CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv
from datetime import timedelta
from homeassistant.util import (Throttle)
from .const import (CONF_BROADCAST_ADDRESS, ORVIBO_ASYNCIO_DATA_KEY)
from . import get_orvibo_class

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=2)
REQUIREMENTS = ['asyncio-orvibo>=1.2']

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Orvibo S20 Switch'
DEFAULT_DISCOVERY = True
DEFAULT_TIMEOUT = 3
DATA_KEY = "switch.orvibo_asyncio"

SERVICE_DISCOVERY = 'orvibo_asyncio_switch_discovery'
DISCOVERY_COMMAND_SCHEMA = vol.Schema({
    vol.Optional(CONF_TIMEOUT, default=10): vol.All(int, vol.Range(min=5)),
    vol.Optional(CONF_BROADCAST_ADDRESS, default='255.255.255.255'): cv.string,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_MAC): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(int, vol.Range(min=1)),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up S20 switches."""
    S20 = get_orvibo_class(hass.data, 'S20')
    PORT = hass.data[ORVIBO_ASYNCIO_DATA_KEY]["PORT"]

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}
    hassdata = hass.data[DATA_KEY]
    host = config.get(CONF_HOST)
    s20_obj = S20((host, PORT), mac=config.get(CONF_MAC), timeout=config.get(CONF_TIMEOUT))
    s20_entity = S20Switch(config.get(CONF_NAME), s20_obj)
    async_add_entities([s20_entity])
    hassdata[host] = s20_entity

    async def async_service_handler(service):
        """Handle a learn command."""
        if service.service != SERVICE_DISCOVERY:
            _LOGGER.error("We should not handle service: %s", service.service)
            return

        switch_data = hass.data[DATA_KEY]
        timeout = service.data.get(CONF_TIMEOUT, 5)
        broadcast = service.data.get(CONF_BROADCAST_ADDRESS, '255.255.255.255s')
        new_switches = []
        disc = await S20.discovery(broadcast_address=broadcast, timeout=timeout)
        for _, v in disc.items():
            if v.hp[0] not in switch_data:
                mac = S20.print_mac(v.mac)
                name = "s_"+mac
                switch_data[v.hp[0]] = {
                    CONF_NAME: name,
                    CONF_MAC: mac,
                    CONF_TIMEOUT: DEFAULT_TIMEOUT,
                    CONF_HOST: v.hp[0],
                    "obj": v}
                _LOGGER.info("Discovered new S20 device %s", v)
                new_switches.append(S20Switch(name, v))
            else:
                _LOGGER.info("Re-Discovered S20 device %s", v)
        if new_switches:
            async_add_entities(new_switches)

    hass.services.async_register(DOMAIN, SERVICE_DISCOVERY, async_service_handler,
                                 schema=DISCOVERY_COMMAND_SCHEMA)


class S20Switch(SwitchDevice):
    """Representation of an S20 switch."""

    def __init__(self, name, s20):
        """Initialize the S20 device."""

        self._name = name
        self._s20 = s20

    @property
    def should_poll(self):
        """Return the polling state."""
        return True

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._s20.state == 1

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Update device state."""
        try:
            await self._s20.subscribe_if_necessary()
        except Exception as ex:
            _LOGGER.exception("Error while fetching S20 state, %s", ex)

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        try:
            if await self._s20.state_change(1):
                await self.async_update_ha_state()
        except Exception as ex:
            _LOGGER.exception("Error while turning on S20, %s", ex)

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        try:
            if await self._s20.state_change(0):
                await self.async_update_ha_state()
        except Exception as ex:
            _LOGGER.exception("Error while turning off S20, %s", ex)
