"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import asyncio
import logging
import time
import socket
from datetime import timedelta
import re

import voluptuous as vol
import binascii
from base64 import b64decode, b64encode

from homeassistant.components.remote import (
    PLATFORM_SCHEMA, DOMAIN, ATTR_NUM_REPEATS, ATTR_DELAY_SECS,
    DEFAULT_DELAY_SECS, RemoteDevice, ATTR_HOLD_SECS, DEFAULT_HOLD_SECS)
from homeassistant.const import (
    CONF_NAME, CONF_HOST, CONF_MAC, CONF_TIMEOUT,
    ATTR_ENTITY_ID, CONF_COMMAND)
import homeassistant.helpers.config_validation as cv
from homeassistant.util.dt import utcnow
from homeassistant.util import Throttle
import traceback

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

REQUIREMENTS = ['broadlink==0.9.0']

_LOGGER = logging.getLogger(__name__)

SERVICE_LEARN = 'broadlink_remote_learn'
DATA_KEY = 'remote.broadlink_remote'

CONF_COMMANDS = 'commands'
CONF_NUMBER_OK_KEYS = "keyn"

DEFAULT_TIMEOUT = 10

LEARN_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): vol.All(str),
    vol.Optional(CONF_TIMEOUT, default=30): vol.All(int, vol.Range(min=10)),
    vol.Optional(CONF_NUMBER_OK_KEYS,default=1): vol.All(int, vol.Range(min=1)),
})

COMMAND_SCHEMA = vol.Schema({
    vol.Required(CONF_COMMAND): vol.All(cv.ensure_list, [cv.string])
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(int, vol.Range(min=0)),
    vol.Optional(CONF_COMMANDS, default={}):
        cv.schema_with_slug_keys(COMMAND_SCHEMA),
}, extra=vol.ALLOW_EXTRA)


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the Xiaomi IR Remote (Chuangmi IR) platform."""
    from .mfzbroadlink import rm
    ip_addr = config.get(CONF_HOST)
    mac_addr = binascii.unhexlify(
        config.get(CONF_MAC).encode().replace(b':', b''))

    # Create handler
    # The Chuang Mi IR Remote Controller wants to be re-discovered every
    # 5 minutes. As long as polling is disabled the device should be
    # re-discovered (lazy_discover=False) in front of every command.

    # Check that we can communicate with device.

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    friendly_name = config.get(CONF_NAME, "broadlink_remote_" +
                               ip_addr.replace('.', '_'))
    timeout = config.get(CONF_TIMEOUT)
    device = rm((ip_addr, 80), mac_addr, timeout)

    #cmnds = fill_commands(config.get(CONF_COMMANDS)
    cmnds = config.get(CONF_COMMANDS)

    xiaomi_miio_remote = BroadlinkRemote(friendly_name, device, binascii.hexlify(mac_addr).decode('utf8'), cmnds)

    hass.data[DATA_KEY][friendly_name] = xiaomi_miio_remote

    async_add_entities([xiaomi_miio_remote])

    async def async_service_handler(service):
        """Handle a learn command."""
        if service.service != SERVICE_LEARN:
            _LOGGER.error("We should not handle service: %s", service.service)
            return

        entity_id = service.data.get(ATTR_ENTITY_ID)
        if entity_id.startswith("remote."):
            entity_id = entity_id[len("remote."):]
        entity = None
        for remote in hass.data[DATA_KEY].values():
            if remote.name == entity_id:
                entity = remote

        if not entity:
            _LOGGER.error("entity_id: '%s' not found", entity_id)
            return

        device = entity._device

        msg = "";
        auth = False
        try:
            auth = await hass.async_add_job(device.auth)
        except socket.timeout:
            msg = "Failed to connect to device, timeout"
        except:
            msg = "Exception in auth: "+traceback.format_exc()
        if len(msg)==0 and not auth:
            msg = "Failed to connect to device"
        if not len(msg):
            timeout = service.data.get(CONF_TIMEOUT, entity.timeout)
            for _ in range(service.data.get(CONF_NUMBER_OK_KEYS,1)):
                auth = await hass.async_add_executor_job(device.enter_learning)
                if auth is None or (auth[0x22] | (auth[0x23] << 8))!=0:
                    msg = "Failed to enter learning mode"
                else:
                    msg = "Press the key you want Home Assistant to learn"
                    _LOGGER.info(msg)
                    hass.components.persistent_notification.async_create(msg, title='Broadlink remote')
                    start_time = utcnow()
                    msg = ''
                    while (utcnow() - start_time) < timedelta(seconds=timeout) and not len(msg):
                        packet = await hass.async_add_job(device.check_data)
                        if packet and not isinstance(packet, int):
                            msg = "Received packet is: r{} or h{}".\
                                      format(b64encode(packet).decode('utf8'),binascii.hexlify(packet).decode('utf8'))
                        
                        await asyncio.sleep(1, loop=hass.loop)
                    if not len(msg):
                        msg = "Did not receive any key"
                _LOGGER.info(msg)
                hass.components.persistent_notification.async_create(msg, title='Broadlink remote')
        else:
            _LOGGER.error(msg)
            hass.components.persistent_notification.async_create(msg, title='Broadlink remote')

    hass.services.async_register(DOMAIN, SERVICE_LEARN, async_service_handler,
                                 schema=LEARN_COMMAND_SCHEMA)


class BroadlinkRemote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""

    def __init__(self, friendly_name, device, unique_id, commands):
        """Initialize the remote."""
        self._name = friendly_name
        self._device = device
        self._unique_id = unique_id
        self._state = "off"
        self._commands = commands

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
    def timeout(self):
        """Return the timeout for learning command."""
        return self._device.timeout

    @property
    def is_on(self):
        """Return False if device is unreachable, else True."""
        return self._state == "on"

    @property
    def should_poll(self):
        """We should not be polled for device up state."""
        return True
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        self._state = "off"
        try:
            if self._device.auth():
                self._state = "on"
            else:
                raise ValueError
        except:
            from .mfzbroadlink import rm
            self._device = rm(self._device.host,self._device.mac,self._device.timeout)
        _LOGGER.info("New state is %s",self._state)

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.error("Device does not support turn_on, "
                      "please use 'remote.send_command' to send commands.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        _LOGGER.error("Device does not support turn_off, "
                      "please use 'remote.send_command' to send commands.")

    def _send_command(self, packet, totretry):
        try:
            if type(packet) is tuple:
                num = packet[1]            
                pid = packet[0][0]
                packet = packet[0][1:]
            else:
                pid = packet[0]
                packet = packet[1:]
                num = -1
            _LOGGER.info("Pid is %s, Len is %d Rep is %d",pid,len(packet),num)
            if pid=='r':
                extra = len(packet) % 4
                if extra > 0:
                    packet = packet + ('=' * (4 - extra))
                payload = b64decode(packet)
                add = "b64dec"
            elif pid=='h':
                payload = binascii.unhexlify(packet)
                add = "unhex"
            elif pid=="t":
                time.sleep(float(packet))
                return True
            else:
                return False
        except:
            _LOGGER.error("Err1: %s ",traceback.format_exc())
            return False
        if num>0:
            if num>100:
                num = 100
            _LOGGER.info("Changing payload")
            payload = bytes([payload[0]])+bytes([num])+payload[2:]
        for retry in range(totretry):
            try:
                _LOGGER.info("I am sending %s, Final len is %d",add,len(payload))
                rv = self._device.send_data(payload)
                if rv is None or (rv[0x22] | (rv[0x23] << 8))!=0:
                    raise ValueError
                self._state = "on"
                break
            except (socket.timeout, ValueError):
                self._state = "off"
                if retry == totretry-1:
                    _LOGGER.error("Failed to send packet to device")
                else:
                    try:
                        from .mfzbroadlink import rm
                        self._device = rm(self._device.host,self._device.mac,self._device.timeout)
                        rv = self._device.auth()
                        _LOGGER.info("Trying to reinit %d", rv)
                    except:
                        pass
        return False
                        
    def command2payloads(self,command):
        _LOGGER.info("Searching for %s", command)
        if command in self._commands:
            _LOGGER.info("%s found in commands", command)
            return self._commands[command][CONF_COMMAND]
        elif command.startswith('@'):
             return [command[1:]]
        else:
            mo = re.search("^ch([0-9]+)$", command)
            if mo is not None and 'ch1' in self._commands:
                commands = [self._commands["ch"+x][CONF_COMMAND][0] for x in command]
            else:
                mo = re.search("^([a-zA-Z0-9_]+)#([0-9]+)$",command)
                if mo is not None:
                    nm = mo.group(1)
                    num = int(mo.group(2))
                    _LOGGER.info("%s rep %d. Searching...", nm,num)
                    if nm in self._commands:
                        _LOGGER.info("%s found in commands", nm)
                        cmdl = self._commands[nm][CONF_COMMAND]
                        return list(zip(cmdl,[num for _ in range(len(cmdl))]))
                    else:
                        return []
                else:
                    commands = [command]
            return commands

    def send_command(self, command, **kwargs):
        """Send a command."""
        num_repeats = kwargs.get(ATTR_NUM_REPEATS,1)

        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        hold = kwargs.get(ATTR_HOLD_SECS, DEFAULT_HOLD_SECS)

        for k in range(num_repeats):
            j = 0
            for c in command:
                payloads = self.command2payloads(c)
                i = 0
                for local_payload in payloads:
                    pause = self._send_command(local_payload,3)
                    i+=1
                    if i<len(payloads) and not pause:
                        time.sleep(hold)
                j+=1
                if j<len(command) and k<num_repeats-1:
                    time.sleep(delay)