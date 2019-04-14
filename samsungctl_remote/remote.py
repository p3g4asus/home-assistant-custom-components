"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import asyncio
import logging
from datetime import timedelta
import re
import functools as ft
import time
import os

import voluptuous as vol

from homeassistant.components.remote import (ATTR_DELAY_SECS,
    DEFAULT_DELAY_SECS, PLATFORM_SCHEMA, RemoteDevice)
from homeassistant.const import (
    CONF_NAME, CONF_FILE_PATH)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle
import traceback
REQUIREMENTS = ['async-upnp-client==0.14.7']
_LOGGER = logging.getLogger(__name__)

DATA_KEY = 'samsungctl_remote'


MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_FILE_PATH,os.path.join(
            os.path.dirname(__file__), 'samsungctl.conf')): cv.string,
}, extra=vol.ALLOW_EXTRA)


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Xiaomi IR Remote (Chuangmi IR) platform."""

    friendly_name = config.get(CONF_NAME)
    fname = config.get(CONF_FILE_PATH)
    # Create handler
    _LOGGER.info("Initializing %s with url %s", friendly_name, fname)
    # The Chuang Mi IR Remote Controller wants to be re-discovered every
    # 5 minutes. As long as polling is disabled the device should be
    # re-discovered (lazy_discover=False) in front of every command.

    # Check that we can communicate with device.

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}
    
    
    unique_id = fname.replace("/","").replace(":","").replace(".","_")

    xiaomi_miio_remote = SamsungCTLRemote(friendly_name, fname, unique_id)

    hass.data[DATA_KEY][friendly_name] = xiaomi_miio_remote

    async_add_entities([xiaomi_miio_remote])



class SamsungCTLRemote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""
    
    CODES = {
        'KEY_POWEROFF',
        'KEY_POWERON',
        'KEY_POWER',
        'KEY_SOURCE',
        'KEY_COMPONENT1',
        'KEY_COMPONENT2',
        'KEY_AV1',
        'KEY_AV2',
        'KEY_AV3',
        'KEY_SVIDEO1',
        'KEY_SVIDEO2',
        'KEY_SVIDEO3',
        'KEY_HDMI',
        'KEY_HDMI1',
        'KEY_HDMI2',
        'KEY_HDMI3',
        'KEY_HDMI4',
        'KEY_FM_RADIO',
        'KEY_DVI',
        'KEY_DVR',
        'KEY_TV',
        'KEY_ANTENA',
        'KEY_DTV',
        'KEY_1',
        'KEY_2',
        'KEY_3',
        'KEY_4',
        'KEY_5',
        'KEY_6',
        'KEY_7',
        'KEY_8',
        'KEY_9',
        'KEY_0',
        'KEY_PANNEL_CHDOWN',
        'KEY_ANYNET',
        'KEY_ESAVING',
        'KEY_SLEEP',
        'KEY_DTV_SIGNAL',
        'KEY_CHUP',
        'KEY_CHDOWN',
        'KEY_PRECH',
        'KEY_FAVCH',
        'KEY_CH_LIST',
        'KEY_AUTO_PROGRAM',
        'KEY_MAGIC_CHANNEL',
        'KEY_VOLUP',
        'KEY_VOLDOWN',
        'KEY_MUTE',
        'KEY_UP',
        'KEY_DOWN',
        'KEY_LEFT',
        'KEY_RIGHT',
        'KEY_RETURN',
        'KEY_ENTER',
        'KEY_REWIND',
        'KEY_STOP',
        'KEY_PLAY',
        'KEY_FF',
        'KEY_REC',
        'KEY_PAUSE',
        'KEY_LIVE',
        'KEY_QUICK_REPLAY',
        'KEY_STILL_PICTURE',
        'KEY_INSTANT_REPLAY',
        'KEY_PIP_ONOFF',
        'KEY_PIP_SWAP',
        'KEY_PIP_SIZE',
        'KEY_PIP_CHUP',
        'KEY_PIP_CHDOWN',
        'KEY_AUTO_ARC_PIP_SMALL',
        'KEY_AUTO_ARC_PIP_WIDE',
        'KEY_AUTO_ARC_PIP_RIGHT_BOTTOM',
        'KEY_AUTO_ARC_PIP_SOURCE_CHANGE',
        'KEY_PIP_SCAN',
        'KEY_VCR_MODE',
        'KEY_CATV_MODE',
        'KEY_DSS_MODE',
        'KEY_TV_MODE',
        'KEY_DVD_MODE',
        'KEY_STB_MODE',
        'KEY_PCMODE',
        'KEY_GREEN',
        'KEY_YELLOW',
        'KEY_CYAN',
        'KEY_RED',
        'KEY_TTX_MIX',
        'KEY_TTX_SUBFACE',
        'KEY_ASPECT',
        'KEY_PICTURE_SIZE',
        'KEY_4_3',
        'KEY_16_9',
        'KEY_EXT14',
        'KEY_EXT15',
        'KEY_PMODE',
        'KEY_PANORAMA',
        'KEY_DYNAMIC',
        'KEY_STANDARD',
        'KEY_MOVIE1',
        'KEY_GAME',
        'KEY_CUSTOM',
        'KEY_EXT9',
        'KEY_EXT10',
        'KEY_MENU',
        'KEY_TOPMENU',
        'KEY_TOOLS',
        'KEY_HOME',
        'KEY_CONTENTS',
        'KEY_GUIDE',
        'KEY_DISC_MENU',
        'KEY_DVR_MENU',
        'KEY_HELP',
        'KEY_INFO',
        'KEY_CAPTION',
        'KEY_CLOCK_DISPLAY',
        'KEY_SETUP_CLOCK_TIMER',
        'KEY_SUB_TITLE',
        'KEY_ZOOM_MOVE',
        'KEY_ZOOM_IN',
        'KEY_ZOOM_OUT',
        'KEY_ZOOM1',
        'KEY_ZOOM2',
        'KEY_WHEEL_LEFT',
        'KEY_WHEEL_RIGHT',
        'KEY_ADDDEL',
        'KEY_PLUS100',
        'KEY_AD',
        'KEY_LINK',
        'KEY_TURBO',
        'KEY_CONVERGENCE',
        'KEY_DEVICE_CONNECT',
        'KEY_11',
        'KEY_12',
        'KEY_FACTORY',
        'KEY_3SPEED',
        'KEY_RSURF',
        'KEY_FF_',
        'KEY_REWIND_',
        'KEY_ANGLE',
        'KEY_RESERVED1',
        'KEY_PROGRAM',
        'KEY_BOOKMARK',
        'KEY_PRINT',
        'KEY_CLEAR',
        'KEY_VCHIP',
        'KEY_REPEAT',
        'KEY_DOOR',
        'KEY_OPEN',
        'KEY_DMA',
        'KEY_MTS',
        'KEY_DNIe',
        'KEY_SRS',
        'KEY_CONVERT_AUDIO_MAINSUB',
        'KEY_MDC',
        'KEY_SEFFECT',
        'KEY_PERPECT_FOCUS',
        'KEY_CALLER_ID',
        'KEY_SCALE',
        'KEY_MAGIC_BRIGHT',
        'KEY_W_LINK',
        'KEY_DTV_LINK',
        'KEY_APP_LIST',
        'KEY_BACK_MHP',
        'KEY_ALT_MHP',
        'KEY_DNSe',
        'KEY_RSS',
        'KEY_ENTERTAINMENT',
        'KEY_ID_INPUT',
        'KEY_ID_SETUP',
        'KEY_ANYVIEW',
        'KEY_MS',
        'KEY_MORE',
        'KEY_MIC',
        'KEY_NINE_SEPERATE',
        'KEY_AUTO_FORMAT',
        'KEY_DNET',
        'KEY_AUTO_ARC_C_FORCE_AGING',
        'KEY_AUTO_ARC_CAPTION_ENG',
        'KEY_AUTO_ARC_USBJACK_INSPECT',
        'KEY_AUTO_ARC_RESET',
        'KEY_AUTO_ARC_LNA_ON',
        'KEY_AUTO_ARC_LNA_OFF',
        'KEY_AUTO_ARC_ANYNET_MODE_OK',
        'KEY_AUTO_ARC_ANYNET_AUTO_START',
        'KEY_AUTO_ARC_CAPTION_ON',
        'KEY_AUTO_ARC_CAPTION_OFF',
        'KEY_AUTO_ARC_PIP_DOUBLE',
        'KEY_AUTO_ARC_PIP_LARGE',
        'KEY_AUTO_ARC_PIP_LEFT_TOP',
        'KEY_AUTO_ARC_PIP_RIGHT_TOP',
        'KEY_AUTO_ARC_PIP_LEFT_BOTTOM',
        'KEY_AUTO_ARC_PIP_CH_CHANGE',
        'KEY_AUTO_ARC_AUTOCOLOR_SUCCESS',
        'KEY_AUTO_ARC_AUTOCOLOR_FAIL',
        'KEY_AUTO_ARC_JACK_IDENT',
        'KEY_AUTO_ARC_CAPTION_KOR',
        'KEY_AUTO_ARC_ANTENNA_AIR',
        'KEY_AUTO_ARC_ANTENNA_CABLE',
        'KEY_AUTO_ARC_ANTENNA_SATELLITE',
        'KEY_PANNEL_POWER',
        'KEY_PANNEL_CHUP',
        'KEY_PANNEL_VOLUP',
        'KEY_PANNEL_VOLDOW',
        'KEY_PANNEL_ENTER',
        'KEY_PANNEL_MENU',
        'KEY_PANNEL_SOURCE',
        'KEY_PANNEL_ENTER',
        'KEY_EXT1',
        'KEY_EXT2',
        'KEY_EXT3',
        'KEY_EXT4',
        'KEY_EXT5',
        'KEY_EXT6',
        'KEY_EXT7',
        'KEY_EXT8',
        'KEY_EXT11',
        'KEY_EXT12',
        'KEY_EXT13',
        'KEY_EXT16',
        'KEY_EXT17',
        'KEY_EXT18',
        'KEY_EXT19',
        'KEY_EXT20',
        'KEY_EXT21',
        'KEY_EXT22',
        'KEY_EXT23',
        'KEY_EXT24',
        'KEY_EXT25',
        'KEY_EXT26',
        'KEY_EXT27',
        'KEY_EXT28',
        'KEY_EXT29',
        'KEY_EXT30',
        'KEY_EXT31',
        'KEY_EXT32',
        'KEY_EXT33',
        'KEY_EXT34',
        'KEY_EXT35',
        'KEY_EXT36',
        'KEY_EXT37',
        'KEY_EXT38',
        'KEY_EXT39',
        'KEY_EXT40',
        'KEY_EXT41',
    }
    
    def _destroy_device(self):
        if self._remote is not None:
            try:
                self._remote.close()
            except:
                pass
            self._remote = None
            self._state = "off"
    
    def _reinit(self):
        from . import samsungctl
        if self._config is None:
            cc = samsungctl.Config.load(self._conffile)
            cc.log_level = samsungctl.Config.LOG_DEBUG
            self._config = cc
        _LOGGER.info("Reiniting %s",self._config)
        self._remote = samsungctl.Remote(self._config)
        if not self._remote.open():
            self._destroy_device()
            self._state = "off"
        else:
            self._state = "on"
        return self._remote
    
    async def reinit(self):
        now = time.time()
        if self._remote is None or now-self._last_init>=60:
            try:
                self._destroy_device()
                
                await self.hass.async_add_job(self._reinit)
                if self._remote is not None:
                    self._last_init = now
            except:
                _LOGGER.error("Reinit error: %s",traceback.format_exc())
                self._destroy_device()
                
        return self._remote
    

    def __init__(self, friendly_name, fpath, unique_id):
        """Initialize the remote."""
        self._name = friendly_name
        self._unique_id = unique_id
        self._state = "off"
        self._config = None
        self._conffile = fpath
        self._remote = None
        self._last_init = 0
        
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
        return self._remote

    @property
    def is_on(self):
        """Return False if device is unreachable, else True."""
        return self._state=="on"

    @property
    def should_poll(self):
        """We should not be polled for device up state."""
        return False

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.error("Device does not support turn_on, "
                      "please use 'remote.send_command' to send commands.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        await self.async_send_command(["KEY_POWEROFF"])
        
    def _send_key(self,key):
        if not self._remote.control(key):
            self._destroy_device()
            return False
        else:
            self._last_init = time.time()
            return True

    async def _send_command(self, packet, totretry):
        if isinstance(packet, float):
            await asyncio.sleep(packet)
            return True
        else:
            for r in range(totretry):
                _LOGGER.info("Pid is %s (%d/%d)",repr(packet),r,totretry)
                if await self.reinit():
                    try:
                        vv = await self.hass.async_add_job(ft.partial(
                            self._send_key, packet))
                        if vv:
                            break
                    except:
                        _LOGGER.error("Send command channel %s",traceback.format_exc())
                        self._destroy_device()
            return False
                        
    def command2payloads(self,command):
        command = command.upper()
        _LOGGER.info("Searching for %s", command)
        if command in SamsungCTLRemote.CODES:
            return [command]
        elif re.search("^[0-9\.]+$",command) is not None:
            return [float(command)]
        else:
            mo = re.search("^ch([0-9]+)$",command)
            if mo is not None:
                cmd = mo.group(1)
                return ["KEY_"+c for c in cmd]
                    
            mo = re.search("^([^#]+)#([0-9]+)$",command)
            if mo is not None:
                cmd = mo.group(1)
                if cmd in SamsungCTLRemote.CODES:
                    return [cmd for _ in range(int(mo.group(2)))]
            return []
        
    async def async_send_command(self, command, **kwargs):
        """Send a command."""
        if await self.reinit():
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