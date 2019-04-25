'''
Created on 25 apr 2019

@author: Matteo
'''
"""
Support for Orvibo S20 Wifi Smart Switches.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/switch.orvibo/
"""
import logging

import voluptuous as vol

from homeassistant.components.switch import (SwitchDevice, PLATFORM_SCHEMA)
from homeassistant.const import (
    CONF_HOST, CONF_NAME, CONF_SWITCHES, CONF_MAC, CONF_DISCOVERY)
import homeassistant.helpers.config_validation as cv
from datetime import timedelta
from homeassistant.util import (Throttle)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=2)
REQUIREMENTS = ['asyncio-orvibo>=1.2']

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Orvibo S20 Switch'
DEFAULT_DISCOVERY = True

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SWITCHES, default=[]):
        vol.All(cv.ensure_list, [{
            vol.Required(CONF_HOST): cv.string,
            vol.Optional(CONF_MAC): cv.string,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string
        }]),
    vol.Optional(CONF_DISCOVERY, default=DEFAULT_DISCOVERY): cv.boolean,
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up S20 switches."""
    from asyncio_orvibo.s20 import S20
    from asyncio_orvibo.orvibo_udp import PORT

    switch_data = {}
    switches = []
    switch_conf = config.get(CONF_SWITCHES, [config])
    for switch in switch_conf:
        switch_data[switch.get(CONF_HOST)] = switch
    if config.get(CONF_DISCOVERY):
        _LOGGER.info("Discovering S20 switches ...")
        disc = await S20.discovery()
        for _,v in disc.items():
            if v.hp[0] not in switch_data:
                mac =  S20.print_mac(v.mac)
                switch_data[v.hp[0]] = {\
                    CONF_NAME: "s_"+mac,\
                    CONF_MAC: mac,\
                    CONF_HOST: v.hp[0],\
                    "obj": v}
            else:
                switch_data[v.hp[0]]["obj"] = v
    
    for _,data in switch_data.items():
        switches.append(S20Switch(data.get(CONF_NAME),\
                      data["obj"] if "obj" in data else\
                       S20((data.get(CONF_HOST),PORT), mac=data.get(CONF_MAC))))

    async_add_entities(switches)


class S20Switch(SwitchDevice):
    """Representation of an S20 switch."""

    def __init__(self, name, s20):
        """Initialize the S20 device."""

        self._name = name
        self._s20 = s20

    @property
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
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
        return self._s20.state==1

    async def async_update(self):
        """Update device state."""
        try:
            await self._s20.subscribe_if_necessary()
        except Exception as ex:
            _LOGGER.exception("Error while fetching S20 state, %s",ex)

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        try:
            await self._s20.state_change(1)
        except Exception as ex:
            _LOGGER.exception("Error while turning on S20, %s",ex)

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        try:
            await self._s20.state_change(0)
        except Exception as ex:
            _LOGGER.exception("Error while turning off S20, %s",ex)
