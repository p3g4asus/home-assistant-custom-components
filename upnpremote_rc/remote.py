"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import asyncio
import logging
from datetime import timedelta
import re

import voluptuous as vol

from homeassistant.components.remote import (ATTR_DELAY_SECS,
    DEFAULT_DELAY_SECS, PLATFORM_SCHEMA, RemoteDevice)
from homeassistant.const import (
    CONF_NAME, CONF_URL, CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle
import traceback

REQUIREMENTS = ['https://github.com/p3g4asus/async_upnp_client/archive/0.14.25.zip#async-upnp-client==0.14.25']
_LOGGER = logging.getLogger(__name__)

DATA_KEY = 'upnpremote_rc'

DEFAULT_TIMEOUT = 5
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)

CONF_DEFAULT_SHARPNESS = "d_sharpness"
CONF_DEFAULT_BRIGHTNESS = "d_brightness"
CONF_DEFAULT_VOLUME = "d_volume"
CONF_DEFAULT_CONTRAST = "d_contrast"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_URL): cv.string,
    vol.Optional(CONF_DEFAULT_SHARPNESS, default=50):
        vol.All(int, vol.Range(min=0,max=100)),
    vol.Optional(CONF_DEFAULT_VOLUME, default=50):
        vol.All(int, vol.Range(min=0,max=100)),
    vol.Optional(CONF_DEFAULT_CONTRAST, default=50):
        vol.All(int, vol.Range(min=0,max=100)),
    vol.Optional(CONF_DEFAULT_BRIGHTNESS, default=50):
        vol.All(int, vol.Range(min=0,max=100)),
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(int, vol.Range(min=0)),
}, extra=vol.ALLOW_EXTRA)


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Xiaomi IR Remote (Chuangmi IR) platform."""

    friendly_name = config.get(CONF_NAME)
    url = config.get(CONF_URL)
    # Create handler
    _LOGGER.info("Initializing %s with url %s", friendly_name, url)
    # The Chuang Mi IR Remote Controller wants to be re-discovered every
    # 5 minutes. As long as polling is disabled the device should be
    # re-discovered (lazy_discover=False) in front of every command.

    # Check that we can communicate with device.

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    
    timeout = config.get(CONF_TIMEOUT)



    defaults = dict(sharpness=config.get(CONF_DEFAULT_SHARPNESS),\
                    brightness=config.get(CONF_DEFAULT_BRIGHTNESS),\
                    contrast=config.get(CONF_DEFAULT_CONTRAST),\
                    volume=config.get(CONF_DEFAULT_VOLUME),
                    mute=-1)
    
    unique_id = url.replace("/","").replace(":","").replace(".","_")

    xiaomi_miio_remote = RCRemote(friendly_name, url, unique_id, timeout,defaults)

    hass.data[DATA_KEY][friendly_name] = xiaomi_miio_remote

    async_add_entities([xiaomi_miio_remote])



class RCRemote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""
    
    RC_STATES = ["contrast","brightness","volume","mute","sharpness"]
    
    #Not used because of polling
    async def set_state(self,newstate):
        if newstate!=self._state:
            self._state = newstate
            await self.async_update_ha_state()
    
    def _destroy_device(self):
        self._service = None
        self._state = "off"
    
    async def reinit(self):
        if not self._service:
            try:
                _LOGGER.warn("Reiniting %s",self._url)
                self._device = await self._factory.async_create_device(self._url)
                # get RenderingControle-service
                self._service = self._device.service('urn:schemas-upnp-org:service:RenderingControl:1')
                self._state = "on"
                return self._service
            except:
                self._state = "off"
                _LOGGER.error("Reinit %s: %s",self._url,traceback.format_exc())
                return None
        else:
            return self._service
    

    def __init__(self, friendly_name, url, unique_id, timeout, defs):
        from async_upnp_client import UpnpFactory
        from async_upnp_client.aiohttp import AiohttpRequester
        """Initialize the remote."""
        self._name = friendly_name
        self._url = url
        self._unique_id = unique_id
        self._state = "off"
        self._device = None
        self._service = None
        self._states = dict.fromkeys(RCRemote.RC_STATES,-5)
        requester = AiohttpRequester(timeout)
        self._factory = UpnpFactory(requester)
        self._defaults = defs

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the remote."""
        return self._name

    @property
    def device(self):
        """Return the remote object."""
        return self._device

    @property
    def is_on(self):
        """Return False if device is unreachable, else True."""
        return self._state=="on"

    @property
    def should_poll(self):
        """We should not be polled for device up state."""
        return True

    @property
    def device_state_attributes(self):
        """Hide remote by default."""
        return self._states

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.error("Device does not support turn_on, "
                      "please use 'remote.send_command' to send commands.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        _LOGGER.error("Device does not support turn_off, "
                      "please use 'remote.send_command' to send commands.")
        
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self,what=None,**kwargs):
        if what is None:
            what = self._states.keys()
        self._state = "off"
        #self._states = dict.fromkeys(RCRemote.RC_STATES,-1)
        if await self.reinit():
            for p in what:
                st = dict()
                try:
                    k = p.title()
                    s = self._service.action('Get'+k)
                    if s is not None:
                        st = await s.async_call(InstanceID=0, Channel='Master')
                        if len(st)>1 and 'Current'+k in st:
                            st = st['Current'+k]
                        elif len(st):
                            st = next(iter(st.values()))
                        else:
                            _LOGGER.error("Update %s rv error %s",p,str(st))
                            self._destroy_device()
                            return
                    else:
                        st = -2
                    self._states[p] = st
                except:
                    self._destroy_device()
                    _LOGGER.error("Update %s error rv = %s: %s",p,st,traceback.format_exc())
                    return
            self._state = "on"

    async def _send_command(self, packet, totretry):
        num = packet[1]            
        packet = packet[0]
        if isinstance(packet, float):
            await asyncio.sleep(packet)
            return True
        else:
            for r in range(totretry):
                _LOGGER.info("Pid is %s, Rep is %d (%d/%d)",packet,num,r,totretry)
                if await self.reinit():
                    if packet=="mute":
                        await self.async_update(["mute"])
                        st = self._states[packet] 
                        if st is not None and st>=0:
                            num = False if st else True
                    s = self._service.action("Set"+packet.title())
                    if s is not None:
                        args = s.in_arguments()
                        kw = dict()
                        for a in args:
                            if a.name=="InstanceID":
                                kw[a.name] = 0
                            elif a.name=="Channel":
                                kw[a.name] = "Master"
                            else:
                                kw[a.name] = num
                        try:
                            await s.async_call(**kw)
                            self._states[packet] = num
                            break
                        except:
                            self._destroy_device()
                            _LOGGER.error("Set %s to %d error %s",packet,num,traceback.format_exc())
                    else:
                        break
            return False
                        
    def command2payloads(self,command):
        command = command.lower()
        _LOGGER.info("Searching for %s", command)
        if command in RCRemote.RC_STATES:
            _LOGGER.info("%s found in commands", command)
            rep = ''
            cmd = command
        else:
            mo = re.search("^([^#_]+)(_[pm])?(#([0-9]+))?$",command)
            if mo is not None:
                cmd = mo.group(1)
                rep = mo.group(4)
            else:
                cmd = ''
        if cmd in RCRemote.RC_STATES:
            if len(rep)==0:
                rep = self._defaults[cmd]
            return [(cmd,int(rep))]
        elif re.search("^t[0-9\.]+$",cmd) is not None:
            return [(float(cmd[1:]),1)]
        else:
            return []
        
    async def async_send_command(self, command, **kwargs):
        """Send a command."""
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        j = 0
        for c in command:
            payloads = self.command2payloads(c)
            k = 0
            pause = False
            for local_payload in payloads:
                pause = await self._send_command(local_payload,3)
                k+=1
                if not pause and k<len(payloads):
                    await asyncio.sleep(delay)
            j+=1
            if not pause and j<len(command):
                await asyncio.sleep(delay)
