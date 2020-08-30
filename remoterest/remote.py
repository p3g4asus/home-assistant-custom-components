"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import asyncio
import binascii
import json
import logging
from datetime import timedelta
from urllib.parse import urlparse

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.remote import (ATTR_DELAY_SECS, ATTR_HOLD_SECS, ATTR_NUM_REPEATS,
                                             DEFAULT_DELAY_SECS, DEFAULT_HOLD_SECS,
                                             PLATFORM_SCHEMA, RemoteDevice)
from homeassistant.const import (CONF_NAME, CONF_TIMEOUT, STATE_OFF, STATE_ON)
from voluptuous.error import UrlInvalid
from voluptuous.schema_builder import message

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

REQUIREMENTS = ['aiohttp>=3.6.1']

_LOGGER = logging.getLogger(__name__)


CONF_URL = 'url'
CONF_BASEURL = 'base_url'
CONF_PARTURL = 'url_path'
CONF_KEYS = 'keys'
CONF_METHOD = 'method'
CONF_PARAMS = 'par'
CONF_LOGRESP = 'logresp'

DEFAULT_TIMEOUT = 5

PARAMS_SCHEMA = vol.Any(cv.string, int, float, None, vol.All(cv.ensure_list, [cv.string, int, float, None, vol.Self]), vol.Self)


def conf_validator_url_or_part(key_dict):
    if (key_dict[CONF_PARTURL] and not key_dict[CONF_URL]) or\
       (key_dict[CONF_URL] and not key_dict[CONF_PARTURL]):
        return key_dict
    else:
        raise vol.Invalid(f'Olnly one between {CONF_URL} and {CONF_PARTURL} is allowed!')
    return key_dict


def conf_validator_baseurl_or_url(remote_dict):
    if not remote_dict[CONF_BASEURL]:
        for _, x in remote_dict[CONF_KEYS].items():
            if not x[CONF_URL]:
                raise vol.Invalid(f'Url has to be specified for each key if {CONF_BASEURL} is not specified')
    return remote_dict


@message('expected a relative URL', cls=UrlInvalid)
def UrlPath(v):
    """Verify that the value is a relative URL.

    >>> s = Schema(Url())
    >>> with raises(MultipleInvalid, 'expected a URL'):
    ...   s(1)
    >>> s('http://w3.org')
    'http://w3.org'
    """
    try:
        parsed = urlparse.urlparse(v)
        if not parsed.path or parsed.netloc or parsed.scheme:
            raise UrlInvalid("must have only a URL path")
        return parsed
    except Exception:
        raise ValueError


KEY_SCHEMA = vol.Schema(vol.All({
    vol.Optional(CONF_URL, default=''): vol.Any(None, '', vol.Url()),
    vol.Optional(CONF_PARTURL, default=''): vol.Any(None, '', UrlPath()),
    vol.Optional(CONF_METHOD, default=''): vol.In(('', 'GET', 'POSTFORM', 'POSTJSON', 'POSTBIN')),
    vol.Optional(CONF_TIMEOUT, default=0):
        vol.All(int, vol.Range(min=0)),
    vol.Optional(CONF_PARAMS, default={}): cv.schema_with_slug_keys(PARAMS_SCHEMA)
}, conf_validator_url_or_part))

PLATFORM_SCHEMA = vol.Schema(vol.All(PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.slug,
    vol.Optional(CONF_LOGRESP, default='DEBUG'): vol.In(('DEBUG', 'INFO')),
    vol.Optional(CONF_BASEURL, default=''): vol.Any(None, '', vol.Url()),
    vol.Optional(CONF_METHOD, default='GET'): vol.In(('GET', 'POSTFORM', 'POSTJSON', 'POSTBIN')),
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(int, vol.Range(min=1)),
    vol.Required(CONF_KEYS): cv.schema_with_slug_keys(KEY_SCHEMA)
}, extra=vol.ALLOW_EXTRA), conf_validator_baseurl_or_url))


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    friendly_name = config.get(CONF_NAME)
    base_url = config.get(CONF_BASEURL)
    method = config.get(CONF_METHOD)
    timeout = config.get(CONF_TIMEOUT)
    logresp = config.get(CONF_LOGRESP)
    keys = config.get(CONF_KEYS)

    lstk = dict()
    for n, desc in keys.items():
        method = desc[CONF_METHOD] if desc[CONF_METHOD] else method
        url = base_url + '/' + desc[CONF_PARTURL] if desc[CONF_PARTURL] else desc[CONF_URL]
        timeout = desc[CONF_TIMEOUT] if desc[CONF_TIMEOUT] else timeout
        lstk[n] = RemoteRestKey(n, url, method, timeout, desc[CONF_PARAMS])

    xiaomi_miio_remote = RestRemote(
        friendly_name,
        lstk,
        logresp)
    lstent = [xiaomi_miio_remote]
    async_add_entities(lstent)


class RemoteRestKey(object):
    """Representation of a RemoteRest key."""
    def __init__(self, name, url, method, timeout, params):
        self._url = url
        self._method = method
        self._timeout = timeout
        self._params = params
        self._name = name

    async def do(self, session):
        if self._method == 'GET':
            pars = dict()
            for k, v in self._params.items():
                pars[k] = v if isinstance(v, (str, int)) else json.dumps(v)
            _LOGGER.info(f"Sending {self._name} ({self._url})...")
            async with session.get(self._url, params=pars) as resp:
                return (resp.status, await resp.text())
        elif self._method == 'POSTJSON':
            async with session.post(self._url, json=self._params) as resp:
                return (resp.status, await resp.text())
        elif self._method == 'POSTFORM':
            async with session.post(self._url, data=self._params) as resp:
                return (resp.status, await resp.text())
        elif self._method == 'POSTBIN':
            async with session.post(self._url, data=binascii.unhexlify(next(iter(self._params.values())))) as resp:
                return (resp.status, await resp.text())


class RestRemote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""

    def __init__(self, friendly_name, keys, logresp):
        """Initialize the remote."""
        self._name = friendly_name
        self._state = STATE_OFF
        self._commands = keys
        self._logresp = logresp

    @property
    def name(self):
        """Return the name of the remote."""
        return self._name

    @property
    def state(self):
        """Return the state."""
        return self._state

    @property
    def is_on(self):
        """Return False if device is unreachable, else True."""
        return self._state != STATE_OFF

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.error("Device does not support turn_on, "
                      "please use 'remote.send_command' to send commands.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        _LOGGER.error("Device does not support turn_off, "
                      "please use 'remote.send_command' to send commands.")

    def get_ttimeout_struct(self, command_list, repeats, delay, ClientTimeout):
        tott = (repeats - 1) * delay
        maxt = 0
        for com in command_list:
            if com in self._commands:
                tim = self._commands[com]._timeout
                if tim > maxt:
                    maxt = tim
                tott += tim
        return ClientTimeout(total=tott, connect=maxt, sock_connect=maxt, sock_read=maxt)

    async def async_send_command(self, command, **kwargs):
        """Send a command."""
        import aiohttp
        if not isinstance(command, (list, tuple)):
            command_list = [command]
        else:
            command_list = command
        num_repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        hold = kwargs.get(ATTR_HOLD_SECS, DEFAULT_HOLD_SECS)
        timestr = self.get_ttimeout_struct(command_list, num_repeats, delay, aiohttp.ClientTimeout)
        async with aiohttp.ClientSession(timeout=timestr) as session:
            for k in range(num_repeats):
                j = 0
                for c in command_list:
                    if c in self._commands:
                        desc = self._commands[c]
                        try:
                            rv = await desc.do(session)
                            if self._logresp == 'DEBUG':
                                _LOGGER.debug(f"Response for {c}: st={rv[0]} txt={rv[1]}")
                            else:
                                _LOGGER.info(f"Response for {c}: st={rv[0]} txt={rv[1]}")
                            if self._state == STATE_OFF:
                                self._state = STATE_ON
                        except Exception as ex:
                            _LOGGER.error(f"Error sending {c}: {ex}")
                            if self._state == STATE_ON:
                                self._state = STATE_OFF
                        j += 1
                        if j < len(command_list) or k < num_repeats - 1:
                            await asyncio.sleep(hold)
                if k < num_repeats - 1:
                    await asyncio.sleep(delay)
