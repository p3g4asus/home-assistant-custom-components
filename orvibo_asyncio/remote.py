"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import logging
import asyncio
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
    ATTR_ENTITY_ID, CONF_COMMAND, CONF_DISCOVERY, STATE_OFF,STATE_ON)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle
import traceback
from .const import CONF_BROADCAST_ADDRESS

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=30)

REQUIREMENTS = ['asyncio-orvibo>=1.2']

_LOGGER = logging.getLogger(__name__)

SERVICE_LEARN = 'orvibo_asyncio_remote_learn'
SERVICE_DISCOVERY = 'orvibo_asyncio_remote_discovery'
DATA_KEY = 'remote.orvibo_asyncio'

CONF_COMMANDS = 'commands'
CONF_REMOTES = 'remotes'
CONF_NUMBER_OK_KEYS = "keyn"

DEFAULT_LEARN_TIMEOUT = 30
DEFAULT_TIMEOUT = 3

LEARN_COMMAND_SCHEMA = vol.Schema({
    vol.Required(ATTR_ENTITY_ID): vol.All(str),
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_LEARN_TIMEOUT): vol.All(int, vol.Range(min=10)),
    vol.Optional(CONF_NUMBER_OK_KEYS,default=1): vol.All(int, vol.Range(min=1)),
})

DISCOVERY_COMMAND_SCHEMA = vol.Schema({
    vol.Optional(CONF_TIMEOUT, default=10): vol.All(int, vol.Range(min=5)),
    vol.Optional(CONF_BROADCAST_ADDRESS, default='255.255.255.255'): cv.string,
})

COMMAND_SCHEMA = vol.Schema({
    vol.Required(CONF_COMMAND): vol.All(cv.ensure_list, [cv.string])
})

REMOTE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(int, vol.Range(min=1)),
    vol.Optional(CONF_COMMANDS, default={}):
        cv.schema_with_slug_keys(COMMAND_SCHEMA),
}, extra=vol.ALLOW_EXTRA)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
   vol.Required(CONF_REMOTES, default=[]):
    vol.All(cv.ensure_list, [REMOTE_SCHEMA]),
    vol.Optional(CONF_DISCOVERY, default=False): cv.boolean,
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    
    from asyncio_orvibo.allone import AllOne
    from asyncio_orvibo.orvibo_udp import PORT

    remote_data = {}
    remotes = []
    remote_conf = config.get(CONF_REMOTES, [config])
    for remote in remote_conf:
        remote_data[remote.get(CONF_HOST)] = remote
    if config.get(CONF_DISCOVERY):
        _LOGGER.info("Discovering AllOne remotes ...")
        disc = await AllOne.discovery()
        for _,v in disc.items():
            if v.hp[0] not in remote_data:
                mac =  AllOne.print_mac(v.mac)
                remote_data[v.hp[0]] = {\
                    CONF_NAME: "s_"+mac,\
                    CONF_MAC: mac,\
                    CONF_HOST: v.hp[0],\
                    "obj": v,
                    CONF_TIMEOUT: DEFAULT_TIMEOUT,
                    CONF_COMMANDS: []}
                _LOGGER.info("Discovered new device %s",v)
            else:
                remote_data[v.hp[0]]["obj"] = v
                _LOGGER.info("Re-Discovered new device %s",v)
    
    for _,data in remote_data.items():
        if "obj" not in data:
            data["obj"] = AllOne((data.get(CONF_HOST),PORT), mac=data.get(CONF_MAC),timeout=data.get(CONF_TIMEOUT))
        remotes.append(AllOneRemote(data.get(CONF_NAME),data.get(CONF_COMMANDS),\
                      data["obj"]))
    hass.data[DATA_KEY] = remote_data
    
    
    async_add_entities(remotes)

    async def async_service_handler(service):
        """Handle a learn command."""
        if service.service == SERVICE_LEARN:
            entity_id = service.data.get(ATTR_ENTITY_ID)
            if entity_id.startswith("remote."):
                entity_id = entity_id[len("remote."):]
            entity = None
            for remote in hass.data[DATA_KEY].values():
                if remote[CONF_NAME] == entity_id:
                    entity = remote
    
            if not entity:
                _LOGGER.error("entity_id: '%s' not found", entity_id)
                return
    
            device = entity["obj"]
            msg = "";
            for _ in range(service.data.get(CONF_NUMBER_OK_KEYS,1)):
                if await device.learn_ir_init():
                    msg = "Press the key you want Home Assistant to learn"
                    _LOGGER.info(msg)
                    hass.components.persistent_notification.async_create(msg, title='AllOne remote')
                    timeout = service.data.get(CONF_TIMEOUT, DEFAULT_LEARN_TIMEOUT)
                    v = await device.learn_ir_get(timeout)
                    if not v:
                        msg = "Did not receive any key"
                    else:
                        msg = "Received packet is: r{} or h{}".\
                                  format(b64encode(v).decode('utf8'),binascii.hexlify(v).decode('utf8'))
                else:
                    msg = "Cannot enter learning mode"
                _LOGGER.info(msg)
                hass.components.persistent_notification.async_create(msg, title='AllOne remote')
        elif service.service == SERVICE_DISCOVERY:
            remote_data = hass.data[DATA_KEY]
            timeout = service.data.get(CONF_TIMEOUT,5)
            broadcast = service.data.get(CONF_BROADCAST_ADDRESS,'255.255.255.255s')
            new_remotes = []
            disc = await AllOne.discovery(broadcast_address=broadcast,timeout=timeout)
            for _,v in disc.items():
                if v.hp[0] not in remote_data:
                    mac =  AllOne.print_mac(v.mac)
                    name = "s_"+mac
                    remote_data[v.hp[0]] = {\
                        CONF_NAME: name,\
                        CONF_MAC: mac,\
                        CONF_HOST: v.hp[0],\
                        "obj": v,
                        CONF_TIMEOUT: DEFAULT_TIMEOUT,
                        CONF_COMMANDS: []}
                    msg = "Discovered new AllOne device %s" % v
                    new_remotes.append(AllOneRemote(name,[],v))
                else:
                    msg = "Re-Discovered AllOne device %s" % v
                _LOGGER.info(msg)
                hass.components.persistent_notification.async_create(
                            msg, title='AllOne remote')
            if new_remotes:
                async_add_entities(new_remotes)
            

    hass.services.async_register(DOMAIN, SERVICE_LEARN, async_service_handler,
                                 schema=LEARN_COMMAND_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCOVERY, async_service_handler,
                                 schema=DISCOVERY_COMMAND_SCHEMA)


class AllOneRemote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""

    def __init__(self, friendly_name, commands, device):
        """Initialize the remote."""
        self._name = friendly_name
        self._device = device
        self._commands = commands
        self._state = 'off'

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
        return self._state == "on"

    @property
    def should_poll(self):
        """We should not be polled for device up state."""
        return True
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        self._state = STATE_ON if await self._device.subscribe_if_necessary() else STATE_OFF
        _LOGGER.info("New state is %s",self._state)

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.error("Device does not support turn_on, "
                      "please use 'remote.send_command' to send commands.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        _LOGGER.error("Device does not support turn_off, "
                      "please use 'remote.send_command' to send commands.")

    async def _send_command(self, packet, totretry):
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
                await asyncio.sleep(float(packet))
                return True
            else:
                return False
        except:
            _LOGGER.error("Err1: %s ",traceback.format_exc())
            return False
        if num<=0:
            num = 1
        for _ in range(num):
            _LOGGER.info("I am sending %s, Final len is %d",add,len(payload))
            await self._device.emit_ir(payload,retry=totretry)
        return False
                        
    def command2payloads(self,command):
        _LOGGER.info("Searching for %s", command)
        if command in self._commands:
            _LOGGER.info("%s found in commands", command)
            return self._commands[command][CONF_COMMAND]
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

    async def async_send_command(self, command, **kwargs):
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
                    pause = await self._send_command(local_payload,3)
                    i+=1
                    if i<len(payloads) and not pause:
                        await asyncio.sleep(hold)
                j+=1
                if j<len(command) and k<num_repeats-1:
                    await asyncio.sleep(delay)