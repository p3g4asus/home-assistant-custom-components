"""Support for Google Assistant Smart Home API."""
from asyncio import gather
from collections.abc import Mapping
from itertools import product
import logging
import re

from homeassistant.util.decorator import Registry

from homeassistant.core import callback
from homeassistant.const import (
    CLOUD_NEVER_EXPOSED_ENTITIES, CONF_NAME, STATE_UNAVAILABLE,
    ATTR_SUPPORTED_FEATURES, ATTR_ENTITY_ID,
)
from homeassistant.components import (
    camera,
    climate,
    cover,
    fan,
    group,
    input_boolean,
    light,
    lock,
    media_player,
    scene,
    script,
    switch,
    vacuum,
)


from . import trait
from .const import (
    TYPE_LIGHT, TYPE_LOCK, TYPE_SCENE, TYPE_SWITCH, TYPE_VACUUM,
    TYPE_THERMOSTAT, TYPE_FAN, TYPE_CAMERA, TYPE_BLINDS,
    CONF_ALIASES, CONF_ROOM_HINT, CONF_STATE_ONOFF_TEMPLATE,
    ERR_FUNCTION_NOT_SUPPORTED, ERR_PROTOCOL_ERROR, ERR_DEVICE_OFFLINE,
    ERR_UNKNOWN_ERROR, CONF_STATE_BRIGHTNESS_TEMPLATE,
    EVENT_COMMAND_RECEIVED, EVENT_SYNC_RECEIVED, EVENT_QUERY_RECEIVED
)
from .helpers import SmartHomeError, RequestData

HANDLERS = Registry()
_LOGGER = logging.getLogger(__name__)

DOMAIN_TO_GOOGLE_TYPES = {
    camera.DOMAIN: TYPE_CAMERA,
    climate.DOMAIN: TYPE_THERMOSTAT,
    cover.DOMAIN: TYPE_BLINDS,
    fan.DOMAIN: TYPE_FAN,
    group.DOMAIN: TYPE_SWITCH,
    input_boolean.DOMAIN: TYPE_SWITCH,
    light.DOMAIN: TYPE_LIGHT,
    lock.DOMAIN: TYPE_LOCK,
    media_player.DOMAIN: TYPE_SWITCH,
    scene.DOMAIN: TYPE_SCENE,
    script.DOMAIN: TYPE_SCENE,
    switch.DOMAIN: TYPE_SWITCH,
    vacuum.DOMAIN: TYPE_VACUUM,
}


def deep_update(target, source):
    """Update a nested dictionary with another nested dictionary."""
    for key, value in source.items():
        if isinstance(value, Mapping):
            target[key] = deep_update(target.get(key, {}), value)
        else:
            target[key] = value
    return target


class _GoogleEntity:
    """Adaptation of Entity expressed in Google's terms."""

    @staticmethod
    def state_entity_id_from_entity_id(entity_id):
        mo = re.search("_kkk_[a-zA-Z0-9_]+", entity_id)
        if mo:
            if mo.start() > 0:
                return entity_id[:mo.start()]
        return None

    def __init__(self, hass, config, state, entity_id=None):
        self.hass = hass
        self.config = config
        self.state = state
        self._traits = None
        self.entity_id_f = entity_id

    @property
    def entity_id(self):
        """Return entity ID."""
        return self.state.entity_id if self.entity_id_f is None else self.entity_id_f

    @property
    def state_entity_id(self):
        return self.state.entity_id

    @callback
    def traits(self):
        """Return traits for entity."""
        if self._traits is not None:
            return self._traits

        state = self.state
        domain = state.domain
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        entity_config = self.config.entity_config.get(self.entity_id, {})
        self._traits = [Trait(self.hass, state, self.config, entity_config)
                        for Trait in trait.TRAITS
                        if Trait.supported(domain, features, entity_config)]
        return self._traits

    async def sync_serialize(self):
        """Serialize entity for a SYNC response.

        https://developers.google.com/actions/smarthome/create-app#actiondevicessync
        """
        state = self.state

        # When a state is unavailable, the attributes that describe
        # capabilities will be stripped. For example, a light entity will miss
        # the min/max mireds. Therefore they will be excluded from a sync.
        if state.state == STATE_UNAVAILABLE:
            return None

        entity_config = self.config.entity_config.get(self.entity_id, {})
        name = (entity_config.get(CONF_NAME) or state.name).strip()

        # If an empty string
        if not name:
            return None

        traits = self.traits()

        # Found no supported traits for this entity
        if not traits:
            return None

        tp = TYPE_LIGHT if state.domain == script.DOMAIN and\
            (CONF_STATE_BRIGHTNESS_TEMPLATE in entity_config or CONF_STATE_ONOFF_TEMPLATE in entity_config) else\
            DOMAIN_TO_GOOGLE_TYPES[state.domain]
        device = {
            'id': self.entity_id,
            'name': {
                'name': name
            },
            'attributes': {},
            'traits': [trait.name for trait in traits],
            'willReportState': False,
            'type': tp,
        }

        # use aliases
        aliases = entity_config.get(CONF_ALIASES)
        if aliases:
            device['name']['nicknames'] = aliases

        for trt in traits:
            device['attributes'].update(trt.sync_attributes())

        room = entity_config.get(CONF_ROOM_HINT)
        if room:
            device['roomHint'] = room
            return device

        dev_reg, ent_reg, area_reg = await gather(
            self.hass.helpers.device_registry.async_get_registry(),
            self.hass.helpers.entity_registry.async_get_registry(),
            self.hass.helpers.area_registry.async_get_registry(),
        )

        entity_entry = ent_reg.async_get(state.entity_id)
        if not (entity_entry and entity_entry.device_id):
            return device

        device_entry = dev_reg.devices.get(entity_entry.device_id)
        if not (device_entry and device_entry.area_id):
            return device

        area_entry = area_reg.areas.get(device_entry.area_id)
        if area_entry and area_entry.name:
            device['roomHint'] = area_entry.name

        return device

    @callback
    def query_serialize(self):
        """Serialize entity for a QUERY response.

        https://developers.google.com/actions/smarthome/create-app#actiondevicesquery
        """
        state = self.state

        if state.state == STATE_UNAVAILABLE:
            return {'online': False}

        attrs = {'online': True}

        for trt in self.traits():
            deep_update(attrs, trt.query_attributes())

        return attrs

    async def execute(self, command, data, params):
        """Execute a command.

        https://developers.google.com/actions/smarthome/create-app#actiondevicesexecute
        """
        executed = False
        for trt in self.traits():
            if trt.can_execute(command, params):
                await trt.execute(command, data, params)
                executed = True
                break

        if not executed:
            raise SmartHomeError(
                ERR_FUNCTION_NOT_SUPPORTED,
                'Unable to execute {} for {}'.format(command,
                                                     self.entity_id))

    @callback
    def async_update(self):
        """Update the entity with latest info from Home Assistant."""
        self.state = self.hass.states.get(self.state.entity_id)

        if self._traits is None:
            return

        for trt in self._traits:
            trt.state = self.state


async def async_handle_message(hass, config, user_id, message):
    """Handle incoming API messages."""
    request_id = message.get('requestId')  # type: str

    data = RequestData(config, user_id, request_id)

    response = await _process(hass, data, message)

    if response and 'errorCode' in response['payload']:
        _LOGGER.error('Error handling message %s: %s',
                      message, response['payload'])

    return response


async def _process(hass, data, message):
    """Process a message."""
    inputs = message.get('inputs')  # type: list

    if len(inputs) != 1:
        return {
            'requestId': data.request_id,
            'payload': {'errorCode': ERR_PROTOCOL_ERROR}
        }

    handler = HANDLERS.get(inputs[0].get('intent'))

    if handler is None:
        return {
            'requestId': data.request_id,
            'payload': {'errorCode': ERR_PROTOCOL_ERROR}
        }

    try:
        result = await handler(hass, data, inputs[0].get('payload'))
    except SmartHomeError as err:
        return {
            'requestId': data.request_id,
            'payload': {'errorCode': err.code}
        }
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception('Unexpected error')
        return {
            'requestId': data.request_id,
            'payload': {'errorCode': ERR_UNKNOWN_ERROR}
        }

    if result is None:
        return None
    return {'requestId': data.request_id, 'payload': result}


@HANDLERS.register('action.devices.SYNC')
async def async_devices_sync(hass, data, payload):
    """Handle action.devices.SYNC request.

    https://developers.google.com/actions/smarthome/create-app#actiondevicessync
    """
    hass.bus.async_fire(
        EVENT_SYNC_RECEIVED,
        {'request_id': data.request_id},
        context=data.context)

    devices = []

    async def add_google_entity(entity, devices):
        serialized = await entity.sync_serialize()

        if serialized is None:
            _LOGGER.debug("No mapping for %s domain", entity.state)
            return

        devices.append(serialized)

    for state in hass.states.async_all():
        if state.entity_id in CLOUD_NEVER_EXPOSED_ENTITIES:
            continue

        if not data.config.should_expose(state):
            continue
        if state.domain == script.DOMAIN and state.entity_id not in data.config.entity_config:
            for ek, _ in data.config.entity_config.items():
                state_entity_id = _GoogleEntity.state_entity_id_from_entity_id(ek)
                if state.entity_id == state_entity_id:
                    await add_google_entity(_GoogleEntity(hass, data.config, state, entity_id=ek), devices)
        else:
            await add_google_entity(_GoogleEntity(hass, data.config, state), devices)

    response = {
        'agentUserId': data.context.user_id,
        'devices': devices,
    }
    _LOGGER.debug("Sync resp %s", str(devices))

    return response


@HANDLERS.register('action.devices.QUERY')
async def async_devices_query(hass, data, payload):
    """Handle action.devices.QUERY request.

    https://developers.google.com/actions/smarthome/create-app#actiondevicesquery
    """
    devices = {}
    for device in payload.get('devices', []):
        devid = device['id']
        state_entity_id = _GoogleEntity.state_entity_id_from_entity_id(devid)
        if state_entity_id is None:
            params_present = False
            state_entity_id = devid
        else:
            params_present = True
        state = hass.states.get(state_entity_id)

        hass.bus.async_fire(
            EVENT_QUERY_RECEIVED,
            {
                'request_id': data.request_id,
                ATTR_ENTITY_ID: state_entity_id,
                'full_entity_id': devid
            },
            context=data.context)

        if not state:
            # If we can't find a state, the device is offline
            devices[devid] = {'online': False}
            continue

        entity = _GoogleEntity(hass, data.config, state, entity_id=devid if params_present else None)
        devices[devid] = entity.query_serialize()

    return {'devices': devices}


@HANDLERS.register('action.devices.EXECUTE')
async def handle_devices_execute(hass, data, payload):
    """Handle action.devices.EXECUTE request.

    https://developers.google.com/actions/smarthome/create-app#actiondevicesexecute
    """
    entities = {}
    results = {}

    for command in payload['commands']:
        for device, execution in product(command['devices'],
                                         command['execution']):
            entity_id = device['id']

            state_entity_id = _GoogleEntity.state_entity_id_from_entity_id(entity_id)
            if state_entity_id is None:
                params_present = False
                state_entity_id = entity_id
            else:
                params_present = True

            hass.bus.async_fire(
                EVENT_COMMAND_RECEIVED,
                {
                    'request_id': data.request_id,
                    ATTR_ENTITY_ID: state_entity_id,
                    "full_entity_id": entity_id,
                    'execution': execution
                },
                context=data.context)

            # Happens if error occurred. Skip entity for further processing
            if entity_id in results:
                continue

            if entity_id not in entities:
                state = hass.states.get(state_entity_id)

                if state is None:
                    results[entity_id] = {
                        'ids': [entity_id],
                        'status': 'ERROR',
                        'errorCode': ERR_DEVICE_OFFLINE
                    }
                    continue

                entities[entity_id] = _GoogleEntity(hass, data.config, state, entity_id=entity_id if params_present else None)

            try:
                await entities[entity_id].execute(execution['command'],
                                                  data,
                                                  execution.get('params', {}))
            except SmartHomeError as err:
                results[entity_id] = {
                    'ids': [entity_id],
                    'status': 'ERROR',
                    'errorCode': err.code
                }

    final_results = list(results.values())

    for entity in entities.values():
        if entity.entity_id in results:
            continue

        entity.async_update()

        final_results.append({
            'ids': [entity.entity_id],
            'status': 'SUCCESS',
            'states': entity.query_serialize(),
        })

    return {'commands': final_results}


@HANDLERS.register('action.devices.DISCONNECT')
async def async_devices_disconnect(hass, data, payload):
    """Handle action.devices.DISCONNECT request.

    https://developers.google.com/actions/smarthome/create#actiondevicesdisconnect
    """
    return None


def turned_off_response(message):
    """Return a device turned off response."""
    return {
        'requestId': message.get('requestId'),
        'payload': {'errorCode': 'deviceTurnedOff'}
    }
