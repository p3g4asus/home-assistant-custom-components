"""Support for Google Assistant Smart Home API."""
import asyncio
from itertools import product
import logging
import re

from homeassistant.util.decorator import Registry

from homeassistant.const import (
    ATTR_ENTITY_ID,
    __version__,
    CLOUD_NEVER_EXPOSED_ENTITIES,
)

from .const import (
    ERR_PROTOCOL_ERROR,
    ERR_DEVICE_OFFLINE,
    ERR_UNKNOWN_ERROR,
    EVENT_COMMAND_RECEIVED,
    EVENT_SYNC_RECEIVED,
    EVENT_QUERY_RECEIVED,
    CONF_STATE_BRIGHTNESS_TEMPLATE,
)
from .helpers import RequestData, GoogleEntity, async_get_entities
from .error import SmartHomeError

HANDLERS = Registry()
_LOGGER = logging.getLogger(__name__)


async def async_handle_message(hass, config, user_id, message):
    """Handle incoming API messages."""
    data = RequestData(config, user_id, message["requestId"], message.get("devices"))

    response = await _process(hass, data, message)

    if response and "errorCode" in response["payload"]:
        _LOGGER.error("Error handling message %s: %s", message, response["payload"])

    return response


async def _process(hass, data, message):
    """Process a message."""
    inputs: list = message.get("inputs")

    if len(inputs) != 1:
        return {
            "requestId": data.request_id,
            "payload": {"errorCode": ERR_PROTOCOL_ERROR},
        }

    handler = HANDLERS.get(inputs[0].get("intent"))

    if handler is None:
        return {
            "requestId": data.request_id,
            "payload": {"errorCode": ERR_PROTOCOL_ERROR},
        }

    try:
        result = await handler(hass, data, inputs[0].get("payload"))
    except SmartHomeError as err:
        return {"requestId": data.request_id, "payload": {"errorCode": err.code}}
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error")
        return {
            "requestId": data.request_id,
            "payload": {"errorCode": ERR_UNKNOWN_ERROR},
        }

    if result is None:
        return None

    return {"requestId": data.request_id, "payload": result}


@HANDLERS.register("action.devices.SYNC")
async def async_devices_sync(hass, data, payload):
    """Handle action.devices.SYNC request.

    https://developers.google.com/assistant/smarthome/develop/process-intents#SYNC
    """
    hass.bus.async_fire(
        EVENT_SYNC_RECEIVED, {"request_id": data.request_id}, context=data.context
    )

    devices = []
    
    async def add_google_entity(entity,devices):
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
        if state.domain==script.DOMAIN and state.entity_id not in data.config.entity_config:
            for ek,_ in data.config.entity_config.items():
                state_entity_id = GoogleEntity.state_entity_id_from_entity_id(ek)
                if state.entity_id==state_entity_id:
                    await add_google_entity(GoogleEntity(hass, data.config, state, entity_id=ek), devices)
        else:
            await add_google_entity(GoogleEntity(hass, data.config, state),devices)

    response = {
        "agentUserId": data.config.agent_user_id or data.context.user_id,
        "devices": devices,
    }
    _LOGGER.debug("Sync resp %s", str(devices))

    return response


@HANDLERS.register("action.devices.QUERY")
async def async_devices_query(hass, data, payload):
    """Handle action.devices.QUERY request.

    https://developers.google.com/assistant/smarthome/develop/process-intents#QUERY
    """
    devices = {}
    for device in payload.get("devices", []):
        devid = device["id"]
        state_entity_id = GoogleEntity.state_entity_id_from_entity_id(devid)
        if state_entity_id is None:
            params_present = False
            state_entity_id = devid
        else:
            params_present = True
        state = hass.states.get(state_entity_id)

        hass.bus.async_fire(
            EVENT_QUERY_RECEIVED,
            {
                "request_id": data.request_id, 
                ATTR_ENTITY_ID: state_entity_id,
                "full_entity_id": devid
            },
            context=data.context,
        )

        if not state:
            # If we can't find a state, the device is offline
            devices[devid] = {"online": False}
            continue

        entity = GoogleEntity(hass, data.config, state, entity_id=devid if params_present else None)
        devices[devid] = entity.query_serialize()

    return {"devices": devices}


@HANDLERS.register("action.devices.EXECUTE")
async def handle_devices_execute(hass, data, payload):
    """Handle action.devices.EXECUTE request.

    https://developers.google.com/assistant/smarthome/develop/process-intents#EXECUTE
    """
    entities = {}
    results = {}

    for command in payload["commands"]:
        for device, execution in product(command["devices"], command["execution"]):
            entity_id = device["id"]
            state_entity_id = GoogleEntity.state_entity_id_from_entity_id(entity_id)
            if state_entity_id is None:
                params_present = False
                state_entity_id = entity_id
            else:
                params_present = True

            hass.bus.async_fire(
                EVENT_COMMAND_RECEIVED,
                {
                    "request_id": data.request_id,
                    ATTR_ENTITY_ID: state_entity_id,
                    "full_entity_id": entity_id,
                    "execution": execution,
                },
                context=data.context,
            )

            # Happens if error occurred. Skip entity for further processing
            if entity_id in results:
                continue

            if entity_id not in entities:
                state = hass.states.get(state_entity_id)

                if state is None:
                    results[entity_id] = {
                        "ids": [entity_id],
                        "status": "ERROR",
                        "errorCode": ERR_DEVICE_OFFLINE,
                    }
                    continue

                entities[entity_id] = GoogleEntity(hass, data.config, state, entity_id=entity_id if params_present else None)

            try:
                await entities[entity_id].execute(data, execution)
            except SmartHomeError as err:
                results[entity_id] = {
                    "ids": [entity_id],
                    "status": "ERROR",
                    **err.to_response(),
                }

    final_results = list(results.values())

    for entity in entities.values():
        if entity.entity_id in results:
            continue

        entity.async_update()

        final_results.append(
            {
                "ids": [entity.entity_id],
                "status": "SUCCESS",
                "states": entity.query_serialize(),
            }
        )

    return {"commands": final_results}


@HANDLERS.register("action.devices.DISCONNECT")
async def async_devices_disconnect(hass, data: RequestData, payload):
    """Handle action.devices.DISCONNECT request.

    https://developers.google.com/assistant/smarthome/develop/process-intents#DISCONNECT
    """
    await data.config.async_deactivate_report_state()
    return None


@HANDLERS.register("action.devices.IDENTIFY")
async def async_devices_identify(hass, data: RequestData, payload):
    """Handle action.devices.IDENTIFY request.

    https://developers.google.com/assistant/smarthome/develop/local#implement_the_identify_handler
    """
    return {
        "device": {
            "id": data.config.agent_user_id,
            "isLocalOnly": True,
            "isProxy": True,
            "deviceInfo": {
                "hwVersion": "UNKNOWN_HW_VERSION",
                "manufacturer": "Home Assistant",
                "model": "Home Assistant",
                "swVersion": __version__,
            },
        }
    }


@HANDLERS.register("action.devices.REACHABLE_DEVICES")
async def async_devices_reachable(hass, data: RequestData, payload):
    """Handle action.devices.REACHABLE_DEVICES request.

    https://developers.google.com/actions/smarthome/create#actiondevicesdisconnect
    """
    google_ids = set(dev["id"] for dev in (data.devices or []))

    return {
        "devices": [
            entity.reachable_device_serialize()
            for entity in async_get_entities(hass, data.config)
            if entity.entity_id in google_ids and entity.should_expose()
        ]
    }


def turned_off_response(message):
    """Return a device turned off response."""
    return {
        "requestId": message.get("requestId"),
        "payload": {"errorCode": "deviceTurnedOff"},
    }
