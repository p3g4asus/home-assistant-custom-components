"""Support for the Xiaomi IR Remote (Chuangmi IR)."""
import asyncio
import logging
from datetime import timedelta
import re
from xml.dom import minidom
from xml.sax.saxutils import escape
import struct
import time

import voluptuous as vol

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    DEFAULT_DELAY_SECS, PLATFORM_SCHEMA, RemoteDevice)
from homeassistant.const import (
    CONF_NAME, CONF_URL, CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import (Throttle, slugify)
import traceback
REQUIREMENTS = ['async-upnp-client==0.14.8']
_LOGGER = logging.getLogger(__name__)

DATA_KEY = 'upnp_maintvagent2_remote'


DEFAULT_TIMEOUT = 5
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_URL): cv.string,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT):
        vol.All(int, vol.Range(min=0))
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
    unique_id = url.replace("/", "").replace(":", "").replace(".", "_")

    xiaomi_miio_remote = MainTVAgent2Remote(friendly_name, url, unique_id, timeout)

    hass.data[DATA_KEY][friendly_name] = xiaomi_miio_remote

    async_add_entities([xiaomi_miio_remote])


class MainTVAgent2Remote(RemoteDevice):
    """Representation of a Xiaomi Miio Remote device."""

    STATES = ["channel", "source", "sourceidx"]

    def _destroy_device(self):
        self._service = None
        self._state = "off"

    async def reinit(self):
        if not self._service:
            try:
                _LOGGER.warn("Reiniting %s", self._url)
                self._device = await self._factory.async_create_device(self._url)
                # get RenderingControle-service
                self._service = self._device.service('urn:samsung.com:service:MainTVAgent2:1')
                await self._get_channels_list()
                await self._get_sources_list()
                if len(self._channels) and len(self._sources):
                    self._state = "on"
                    return self._service
                else:
                    self._destroy_device()
            except BaseException as ex:
                self._state = "off"
                _LOGGER.error("Reinit Error %s: %s", self._url, ex)
                return None
            except Exception:
                self._state = "off"
                _LOGGER.error("Reinit Error %s", self._url)
                return None
        else:
            return self._service

    def __init__(self, friendly_name, url, unique_id, timeout):
        from async_upnp_client import UpnpFactory
        from async_upnp_client.aiohttp import AiohttpRequester
        """Initialize the remote."""
        self._name = friendly_name
        self._url = url
        self._unique_id = unique_id
        self._state = "off"
        self._device = None
        self._service = None
        self._states = dict.fromkeys(MainTVAgent2Remote.STATES, '-5')
        requester = AiohttpRequester(timeout)
        self._factory = UpnpFactory(requester, disable_unknown_out_argument_error=True)
        self._sources = []
        self._channels = {}
        self._channel_list_type = None
        self._channel_satellite_id = None
        self._current_source = ''
        self._current_source_t = 0
        self._current_channel_t = 0
        self._current_source_l_t = 0
        self._current_channel_l_t = 0

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
        return self._state == "on"

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

    @staticmethod
    async def fetch_page(url, timeout=10):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                assert response.status == 200
                return await response.read()

    async def _get_channels_list(self):
        now = time.time()
        if (not len(self._channels) or now - self._current_channel_l_t >= 600) and self._service:
            res = dict()
            try:
                res = await self._service.action("GetChannelListURL").async_call()
                self._channel_list_type = res["ChannelListType"]
                self._channel_satellite_id = 0 if "SatelliteID" not in res or res["SatelliteID"] is None else res["SatelliteID"]
                webContent = await MainTVAgent2Remote.fetch_page(res['ChannelListURL'])
                self._channels = Channel._parse_channel_list(webContent)
                self._current_channel_l_t = now
            except Exception:
                _LOGGER.error("GetChannelsList error rv = %s: %s", str(res), traceback.format_exc())
                self._channels = {}

    async def _get_sources_list(self):
        now = time.time()
        if (not len(self._sources) or now - self._current_source_l_t >= 600) and self._service:
            res = dict()
            try:
                res = await self._service.action("GetSourceList").async_call()
                xmldoc = minidom.parseString(res['SourceList'])
                sources = xmldoc.getElementsByTagName('Source')
                self._sources = []
                i = 0
                for s in sources:
                    src = Source(s, i)
                    i += 1
                    if src.sname != 'av' and src.sname != 'AV':
                        self._sources.append(src)
                self._current_source_l_t = now
            except Exception:
                _LOGGER.error("GetSourceList error rv = %s: %s", res, traceback.format_exc())
                self._sources = []

    async def _get_current_source(self):
        now = time.time()
        rv = self._states['source']
        if not len(rv) or now-self._current_source_t >= 10:
            try:
                res = await self._service.action("GetCurrentExternalSource").async_call()
                if 'Result' in res and res['Result'] == "OK":
                    self._current_source_t = now
                    rv = res['CurrentExternalSource']
                    if self._states["source"] != rv:
                        self._states["source"] = rv
                        c = next((x.idx for x in self._sources if x.sname == rv), 0)
                        self._states["sourceidx"] = c
                else:
                    rv = ''
            except Exception:
                _LOGGER.error("GetCurentExternalSource error %s", traceback.format_exc())
                rv = ''
        return rv

    async def _get_current_channel(self):
        now = time.time()
        rv = self._states["channel"]
        if not len(rv) or now - self._current_channel_t >= 10:
            try:
                res = await self._service.action("GetCurrentMainTVChannel").async_call()
                if 'Result' in res and res['Result'] == "OK":
                    self._current_channel_t = now
                    xmldoc = minidom.parseString(res['CurrentChannel'])
                    c = Channel(xmldoc)
                    rv = c.major_ch
                    self._states["channel"] = rv
                else:
                    rv = ''
            except Exception:
                _LOGGER.error("GetCurrentMainTVChannel error %s", traceback.format_exc())
                rv = ''
        return rv

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self, **kwargs):
        self._state = "off"
        err = 0
        if await self.reinit():
            src = await self._get_current_source()
            if not len(src):
                err += 1
            chan = await self._get_current_channel()
            if not len(chan):
                err += 1
            if err == 2:
                self._destroy_device()
            else:
                self._state = "on"

    async def _send_command(self, packet, totretry):
        if isinstance(packet, float):
            await asyncio.sleep(packet)
            return True
        else:
            for r in range(totretry):
                _LOGGER.info("Pid is %s (%d/%d)", repr(packet), r, totretry)
                if await self.reinit():
                    try:
                        if isinstance(packet, Channel):
                            vv = await self._service.action("SetMainTVChannel").async_call(
                                     **packet.as_params(self._channel_list_type, self._channel_satellite_id))
                            if 'Result' in vv and vv['Result'] == "OK":
                                self._states["channel"] = packet.dispno
                                break
                            else:
                                _LOGGER.error("Change channel rv %s", str(vv))
                                self._destroy_device()
                        elif isinstance(packet, Source):
                            vv = await self._service.action("SetMainTVSource").async_call(**packet.as_params())
                            if 'Result' in vv and vv['Result'] == "OK":
                                self._states["source"] = packet.sname
                                self._states["sourceidx"] = packet.idx
                                break
                            else:
                                _LOGGER.error("Change source rv %s", str(vv))
                        elif packet == "reloadchannels":
                            self._current_channel_l_t = 0
                            await self._get_channels_list()
                            if self._current_channel_l_t > 0:
                                break
                        elif packet == "reloadsources":
                            self._current_source_l_t = 0
                            await self._get_sources_list()
                            if self._current_source_l_t > 0:
                                break
                    except Exception:
                        _LOGGER.error("Send command channel %s", traceback.format_exc())
                        self._destroy_device()
            return False

    def command2payloads(self, command):
        command = command.lower()
        _LOGGER.info("Searching for %s", command)
        if command == "reloadchannels" or command == "reloadsources":
            return [command]
        elif re.search(r"^t[0-9\.]+$", command) is not None:
            return [float(command[1:])]
        mo = re.search(r"^ch([0-9]+)$", command)
        if mo is not None:
            c = mo.group(1)
            if c in self._channels:
                return [self._channels[c]]
            else:
                return []
        mo = re.search(r"^sr([0-9]+)$", command)
        if mo is not None:
            c = int(mo.group(1))
            if len(self._sources) > c:
                return [self._sources[c]]
            else:
                return []
        c = next((x for x in self._sources if x.sname == command or slugify(x.sname) == command), None)
        if c is not None:
            return [c]
        else:
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
                    pause = await self._send_command(local_payload, 3)
                    k += 1
                    if not pause and k < len(payloads):
                        await asyncio.sleep(delay)
                j += 1
                if not pause and j < len(command):
                    await asyncio.sleep(delay)


class ContextException(Exception):
    """An Exception class with context attached to it, so a caller can catch a
    (subclass of) ContextException, add some context with the exception's
    add_context method, and rethrow it to another callee who might again add
    information."""

    def __init__(self, msg, context=[]):
        self.msg = msg
        self.context = list(context)

    def __str__(self):
        if self.context:
            return '%s [context: %s]' % (self.msg, '; '.join(self.context))
        else:
            return self.msg

    def add_context(self, context):
        self.context.append(context)


class ParseException(ContextException):
    """An Exception for when something went wrong parsing the channel list."""
    pass


def _getint(buf, offset):
    """Helper function to extract a 16-bit little-endian unsigned from a char
    buffer 'buf' at offset 'offset'..'offset'+2."""
    x = struct.unpack('<H', buf[offset:offset + 2])
    return x[0]


class Channel(object):
    """Class representing a Channel from the TV's channel list."""

    @staticmethod
    def _parse_channel_list(channel_list):
        """Splits the binary channel list into channel entry fields and returns a list of Channels."""

        # The channel list is binary file with a 4-byte header, containing 2 unknown bytes and
        # 2 bytes for the channel count, which must be len(list)-4/124, as each following channel
        # is 124 bytes each. See Channel._parse_dat for how each entry is constructed.

        if len(channel_list) < 128:
            raise ParseException(('channel list is smaller than it has to be for at least '
                                  'one channel (%d bytes (actual) vs. 128 bytes' % len(channel_list)),
                                 ('Channel list: %s' % repr(channel_list)))

        if (len(channel_list)-4) % 124 != 0:
            raise ParseException(('channel list\'s size (%d) minus 128 (header) is not a multiple of '
                                  '124 bytes' % len(channel_list)),
                                 ('Channel list: %s' % repr(channel_list)))

        actual_channel_list_len = (len(channel_list)-4) / 124
        expected_channel_list_len = _getint(channel_list, 2)
        if actual_channel_list_len != expected_channel_list_len:
            raise ParseException(('Actual channel list length ((%d-4)/124=%d) does not equal expected '
                                  'channel list length (%d) as defined in header' % (
                                    len(channel_list),
                                    actual_channel_list_len,
                                    expected_channel_list_len))
                                 ('Channel list: %s' % repr(channel_list)))

        channels = {}
        pos = 4
        while pos < len(channel_list):
            chunk = channel_list[pos:pos+124]
            try:
                ch = Channel(chunk)
                channels[ch.dispno] = ch
            except ParseException as pe:
                pe.add_context('chunk starting at %d: %s' % (pos, repr(chunk)))
                raise pe

            pos += 124

        _LOGGER.info('Parsed %d channels', len(channels))
        return channels

    def __init__(self, from_dat):
        """Constructs the Channel object from a binary channel list chunk."""
        if isinstance(from_dat, minidom.Node):
            self._parse_xml(from_dat)
        else:
            self._parse_dat(from_dat)

    def _parse_xml(self, root):
        try:
            self.ch_type = root.getElementsByTagName('ChType')[0].childNodes[0].nodeValue
            self.major_ch = root.getElementsByTagName('MajorCh')[0].childNodes[0].nodeValue
            self.minor_ch = root.getElementsByTagName('MinorCh')[0].childNodes[0].nodeValue
            self.ptc = root.getElementsByTagName('PTC')[0].childNodes[0].nodeValue
            self.prog_num = root.getElementsByTagName('ProgNum')[0].childNodes[0].nodeValue
            self.dispno = self.major_ch
            self.title = ''
        except Exception:
            raise ParseException("Wrong XML document")

    def _parse_dat(self, buf):
        """Parses the binary data from a channel list chunk and initilizes the
        member variables."""

        # Each entry consists of (all integers are 16-bit little-endian unsigned):
        #   [2 bytes int] Type of the channel. I've only seen 3 and 4, meaning
        #                 CDTV (Cable Digital TV, I guess) or CATV (Cable Analog
        #                 TV) respectively as argument for <ChType>
        #   [2 bytes int] Major channel (<MajorCh>)
        #   [2 bytes int] Minor channel (<MinorCh>)
        #   [2 bytes int] PTC (Physical Transmission Channel?), <PTC>
        #   [2 bytes int] Program Number (in the mux'ed MPEG or so?), <ProgNum>
        #   [2 bytes int] They've always been 0xffff for me, so I'm just assuming
        #                 they have to be :)
        #   [4 bytes string, \0-padded] The (usually 3-digit, for me) channel number
        #                               that's displayed (and which you can enter), in ASCII
        #   [2 bytes int] Length of the channel title
        #   [106 bytes string, \0-padded] The channel title, in UTF-8 (wow)

        t = _getint(buf, 0)
        if t == 4:
            self.ch_type = 'CDTV'
        elif t == 3:
            self.ch_type = 'CATV'
        elif t == 2:
            self.ch_type = 'DTV'
        else:
            raise ParseException('Unknown channel type %d' % t)

        self.major_ch = _getint(buf, 2)
        self.minor_ch = _getint(buf, 4)
        self.ptc = _getint(buf, 6)
        self.prog_num = _getint(buf, 8)

        if _getint(buf, 10) != 0xffff:
            raise ParseException('reserved field mismatch (%04x)' % _getint(buf, 10))

        self.dispno = buf[12:16].decode('utf-8').rstrip('\x00')

        title_len = _getint(buf, 22)
        self.title = buf[24:24+title_len].decode('utf-8')

    def display_string(self):
        """Returns a unicode display string, since both __repr__ and __str__ convert it
        to ascii."""

        return u'[%s] % 4s %s' % (self.ch_type, self.dispno, self.title)

    def __repr__(self):
        # return self.as_xml
        return '<Channel %s %s ChType=%s MajorCh=%d MinorCh=%d PTC=%d ProgNum=%d>' % \
            (self.dispno, repr(self.title), self.ch_type, self.major_ch, self.minor_ch, self.ptc,
             self.prog_num)

    @property
    def as_xml(self):
        """The channel list as XML representation for SetMainTVChannel."""

        return ('<?xml version="1.0" encoding="UTF-8" ?><Channel><ChType>%s</ChType><MajorCh>%d'
                '</MajorCh><MinorCh>%d</MinorCh><PTC>%d</PTC><ProgNum>%d</ProgNum></Channel>') % \
            (escape(self.ch_type), self.major_ch, self.minor_ch, self.ptc, self.prog_num)

    def as_params(self, chtype, sid):
        return {'ChannelListType': chtype, 'Channel': self.as_xml, 'SatelliteID': sid}


class Source(object):
    def __init__(self, root, idx):
        name = root.getElementsByTagName('SourceType')
        sid = root.getElementsByTagName('ID')
        self.sname = name[0].childNodes[0].nodeValue
        self.sid = int(sid[0].childNodes[0].nodeValue)
        self.idx = idx

    def __repr__(self):
        return '<Source %s Sid=%d Idx=%d>' % \
            (repr(self.sname), self.sid, self.idx)

    def as_params(self):
        return {'Source': self.sname, 'ID': self.sid, 'UiID': self.sid}
