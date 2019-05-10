

# home-assistant-custom-components

This is a set of custom components for home-assistant. To install any of them simply place its folder inside your `<config directory>/custom_components` folder.
Table of components:
 - [broadlink_asyncio](#broadlink_asyncio): RemoteDevice component that supports Broadlink RM smart remotes.
 - [orvibo_asyncio switch](#orvibo_asyncio-switch): SwitchDevice component that supports Orvibo s20 smart plugs.
 - [orvibo_asyncio remote](#orvibo_asyncio-remote): RemoteDevice component that supports Orvibo Allone smart remotes.
 - [gocomma](#gocomma): RemoteDevice component that supports Gocomma r9 smart remotes (and maybe also other Tuya smart remotes).
 - [samsungctl_remote](#samsungctl_remote): RemoteDevice component that uses samsung TV network protocol (see [samsungctl](https://github.com/kdschlosser/samsungctl)).
 - [upnp_renderingcontrol](#upnp_renderingcontrol): RemoteDevice component that uses UPNP RenderingControl service to control volume, brightness, contrast, sharpness, muteness of a smart TV device.
 - [upnp_maintvagent2](#upnp_maintvagent2): RemoteDevice component that uses UPNP MainTVAgent2 service to set channel and video source of some Samsung smart TVs.
 - [google_assistant](#google_assistant): A modified version of home-assistant [google-assistant component](https://www.home-assistant.io/components/google_assistant/) to support calling script that need parameters.

## broadlink_asyncio

RemoteDevice component that supports Broadlink RM devices. To get started put `/broadlink_asyncio/` here:
`<config directory>/custom_components/broadlink_asyncio/`

### <a name="broadlink_asyncio_configuration"></a>Example configuration.yaml
```yaml
remote:
    - platform: broadlink_asyncio
      name: diningroom
      host: $ip_addr$
      mac: $mac_addr$
      timeout: $timeout$
      remotes:
          maintv:
              ch0:
                  - $commandstring_ch0$
              ch1:
                  - $commandstring_ch1$
              mute:
                  - $commandstring_mute$
              volume_p:
                  - $commandstring_volume_p$
              volume_m:
                  - $commandstring_volume_m$
          hifi:
              source:
                  - $commandstring_source1$
                  - $commandstring_source2$
              equalization:
                  - $commandstring_equalization$
```

### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `broadlink_asyncio` | `broadlink_asyncio`
**name (Required)** | Name your device | `diningroom`
**host (Required)** | The ip address of your Broadlink RM | `192.168.25.44`
**mac (Required)** | The mac address of your Broadlink RM | `AA:BB:CC:DD:EE:FF` <br/>or<br/> `AABBCCDDEEFF`
**timeout (Optional)** | Timeout in seconds used in the communication with your Broadlink RM. **Default** `3` | `5`
**<a name="broadlink_asyncio_remotes"></a>remotes (Optional)** | Map (dictionary) of the devices that you want to control with your Broadlink RM. Each key is the name of the device to control. Each value is itself a dictionary whose keys are the key button names and values are a list of the commands associated to the key button. **Default** `empty` | See [above](#broadlink_asyncio_configuration)

The command string can be either
 - `h` followed by the command learned by the device in hex format: e.g.:  `h26007600082008250817085b082908290825081c080001a808210852081808180818081c0718071`
 - `r` followed by the command learned by the device in base64 encoded format: e.g.: `rihGyESYCpAYSAqQGEgKkBiYCMAIcAjoCHAI6AiYCRAIcAkQCHAKkBiYC`
 - `t` followed by a floating point number. This represents a delay in seconds: e.g.: `t0.5`

### <a name="broadlink_asyncio_entities"></a>Entities created
This component will create one entity for each devices in the [`remotes`](#broadlink_asyncio_remotes) map and an additional entity. The above example will create 3 entities with the following ids:
 - `remote.diningroom_maintv`
 - `remote.diningroom_hifi`
 - `remote.diningroom`

### <a name="broadlink_asyncio_commands"></a>Sending commands
Use the service `remote.send_command` with the following data

parameter| description| example
:--- | :---| :---
**entity_id (Required)** | use any of the entities created | `remote.diningroom_maintv`
**command (Required)** | list of commands to send. It must contain commands defined in the [`remotes`](#broadlink_asyncio_remotes) map. It can also contain delay commands. | `["ch1","t0.5","ch0"]` <br/> `["101"]` will also work to press in sequence `ch1`, `ch0` and `ch1` <br/> `["volume_p#10"]` can be used to send 10 times `volume_p` command
**num_repeats (Optional)** | Number of repetitions of the command specified **Default** `1` | `2`
**hold_secs (Optional)** | Seconds to be waited between each command in list **Default** `0` | `0.5`
**delay_secs (Optional)** | Seconds to be waited between each repetition of command list **Default** `0` | `1`

### <a name="broadlink_asyncio_learning"></a>Learning remote key buttons
Use the service  `remote.broadlink_asycio_learn` with the following data

parameter| description| example
:--- | :---| :---
**entity_id (Required)** | use the entity that is not associated to any device name | `remote.diningroom`
**timeout (Optional)** | Seconds to be waited at most for key press **Default** `30` | `10`
**keys (Optional)** | list of the names of the keys to learn **Default** `["NA_1"]` | `["ch0","ch1","enter","back","volume_p"]`

On service invocation the Broadlink RM will be put in learning mode and ask for keys to learn. On key reception the command string to be put in the configuration file will be written in the persistent notification section of the lovelace GUI (identified by the :bell:), and will be added in the `last_learned` dict in entity `attributes`. 
To show a notification that asks for the key to be pressed the [home-assistant alerting service](https://www.home-assistant.io/components/alert) can be used. 
For example:
```yaml
notify:
    - platform: html5
      name: html5notif
      vapid_pub_key: $pub_key$
      vapid_prv_key: $prv_key$
      vapid_email: $vapid_email$
alert:
    learning_remote:
          name: Remote learning
          entity_id: remote.diningroom
          repeat: 30
          state: learning_key
          can_acknowledge: true
          message: Please press {{ states.remote.diningroom.attributes.key_to_learn }}
          notifiers:
              - html5notif
```
For more informations on how to configure html5 notifications in home-assistant have a look [here](https://www.home-assistant.io/components/html5).

### <a name="broadlink_asyncio_state"></a>Entity state and attributes

The state of the entities created by this component can take one of the following values:

value| meaning
:--- | :---
**on** | the Broadlink RM device is up and running but not in learning mode
**off** | the Broadlink RM device does not respond to commands: probably it is switched off
**learning_init** | the Broadlink RM is entering learning mode
**learning_ok** | the Broadlink RM has entered learning mode correctly
**learning_key** | the Broadlink RM device is in learning mode and is waiting for a key press

The `attributes` dict of the entity created has the following fields:

key| value
:--- | :---
**key_to_learn** | when the state is `learning_key` it contains the name of the key that should be pressed
**last_learned** | a dict that contains the learned keys since last home-assistant switch off. The keys of the dictionary are the remote key names and the values are the hexadecimal strings that can be used in the [`remotes`](#broadlink_asyncio_remotes) map command strings with the `h` prefix.


## orvibo_asyncio switch

Switch component that supports Orvibo s20 devices. To get started put `/orvibo_asyncio/(switch|__init__).pi` here:
`<config directory>/custom_components/orvibo_asyncio/`.  Please note that this component is NOT compatible with the official `orvibo` component. They should not be enabled simultaneously.

### <a name="orvibo_asyncio_switch_configuration"></a>Example configuration.yaml

```yaml
switch:
    - platform: orvibo_asyncio
      host: $ip_addr$
      mac: $mac_addr$
      name: lamp
      timeout: $timeout$
```
### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `orvibo_asyncio` | `orvibo_asyncio`
**name (Required)** | Name your device | `lamp`
**host (Required)** | The ip address of your Orvibo s20 | `192.168.25.44`
**mac (Required)** | The mac address of your Orvibo s20 | `AA:BB:CC:DD:EE:FF` <br/>or<br/> `AABBCCDDEEFF`
**timeout (Optional)** | Timeout in seconds used in the communication with the Orvibo s20. **Default** `3` | `5`

### Entities created

The component will create an entity for each switch defined in the switch array. The above example will create and register an entity with id `switch.lamp`.

### Sending commands

Use the services `switch.turn_on`, `switch.turn_off` and `switch.toggle` respectively to turn on, turn off or toggle your s20 smart plug. The only parameter that they need is the switch `entity_id`.

### <a name="orvibo_asyncio_discovery"></a>Discovery service

On platform initialization the service `switch.orvibo_asyncio_switch_discovery` is registered. It can be used to discover new, unknown Orvibo s20 devices.
The service can be called with the following data:

parameter| description| example
:--- | :---| :---
**timeout (Optional)** | stop discovery after the given timeout in seconds. **Default** `10` | `30`
**broadcast_address (Optional)** | use the given broadcast address to look for s20 smart plugs. **Default** `255.255.255.255` | `192.168.25.255`

If any s20 device is found during discovery, an entity  for each previously unknown switch is created with id `switch.s_aabbccddeeff` where `aa:bb:cc:dd:ee:ff` is the s20 mac address.

### Entity state and attributes

The state of the entities created by this component can take one of the following values:

value| meaning
:--- | :---
**on** | the s20 switch is on
**off** | the s20 switch is off

The switch entity does not provide attributes.

## orvibo_asyncio remote

Remote component that supports Orvibo Allone devices. To get started put `/orvibo_asyncio/(remote|__init__).py` here:
`<config directory>/custom_components/orvibo_asyncio/`.
Please note that this component is NOT compatible with the official `orvibo` component. They should not be enabled simultaneously.

### <a name="orvibo_asyncio_remote_configuration"></a>Example configuration.yaml

```yaml
remote:
    - platform: orvibo_asyncio
      host: $ip_addr$
      mac: $mac_addr$
      name: diningroom
      timeout: $timeout$
      remotes:
          maintv:
              ch0:
                  - $commandstring_ch0$
              ch1:
                  - $commandstring_ch1$
              mute:
                  - $commandstring_mute$
              volume_p:
                  - $commandstring_volume_p$
              volume_m:
                  - $commandstring_volume_m$
          hifi:
              source:
                  - $commandstring_source$
              equalization:
                  - $commandstring_equalization$
```
### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `orvibo_asyncio` | `orvibo_asyncio`
**name (Required)** | Name your device | `diningroom`
**host (Required)** | The ip address of your Orvibo Allone | `192.168.25.44`
**mac (Required)** | The mac address of your Orvibo Allone | `AA:BB:CC:DD:EE:FF` <br/>or<br/> `AABBCCDDEEFF`
**timeout (Optional)** | Timeout in seconds used in the communication with the Orvibo Allone. **Default** `3` | `5`
**remotes (Optional)** | See [broadlink_asyncio](#broadlink_asyncio_remotes). **Default** `empty` | See [above](#orvibo_asyncio_remote_configuration)

### Entities created


The component will create an entity for each remote defined in the Allone array.  The above example will create 3 entities with the following ids:
 - `remote.diningroom_maintv`
 - `remote.diningroom_hifi`
 - `remote.diningroom`

### Sending commands
See [broadlink_asyncio](#broadlink_asyncio_commands).

### Learning remote key buttons
See [broadlink_asyncio](#broadlink_asyncio_learning).

### Discovery service

The service name is `remote.orvibo_asyncio_remote_discovery`. New entities will be crated in the `remote` domain.
See [orvibo_asyncio](#orvibo_asyncio_discovery) for details.

### Entity state and attributes
See [broadlink_asyncio](#broadlink_asyncio_state).

## gocomma

RemoteDevice component that supports Gocomma r9 and maybe also other standard Tuya smart remote devices. To get started put `/gocomma/` here:
`<config directory>/custom_components/gocomma/`

### <a name="gocomma_configuration"></a>Example configuration.yaml
```yaml
remote:
    - platform: gocomma
      name: diningroom
      host: $ip_addr$
      id: $tuya_id$
      key: $tuya_key$
      timeout: $timeout$
      remotes:
          maintv:
              ch0:
                  - $commandstring_ch0$
              ch1:
                  - $commandstring_ch1$
              mute:
                  - $commandstring_mute$
              volume_p:
                  - $commandstring_volume_p$
              volume_m:
                  - $commandstring_volume_m$
          hifi:
              source:
                  - $commandstring_source1$
                  - $commandstring_source2$
              equalization:
                  - $commandstring_equalization$
```

### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `gocomma` | `gocomma`
**name (Required)** | Name your device | `diningroom`
**host (Required)** | The ip address of your Gocomma r9 | `192.168.25.44`
**id (Required)** | The Tuya id of your Gocomma r9. See [here](https://github.com/clach04/python-tuya/wiki) to know how to get it | `28062578bcd1bcda2cf9`
**key (Required)** | The Tuya key of your Gocomma r9. See [here](https://github.com/clach04/python-tuya/wiki) to know how to get it | `1234567890abcdef`
**timeout (Optional)** | Timeout in seconds used in the communication with your Gocomma r9. **Default** `3` | `5`
**remotes (Optional)** | See [broadlink_asyncio](#broadlink_asyncio_remotes). **Default** `empty` | See [above](#gocomma_configuration)

### Entities created
See [broadlink_asyncio](#broadlink_asyncio_entities).

### Sending commands
See [broadlink_asyncio](#broadlink_asyncio_commands).

### Learning remote key buttons
See [broadlink_asyncio](#broadlink_asyncio_learning).

### Entity state and attributes
See [broadlink_asyncio](#broadlink_asyncio_state).

## samsungctl_remote

RemoteDevice component that uses samsung TV network protocol (see [samsungctl](https://github.com/kdschlosser/samsungctl)). To get started put `/samsungctl_remote/` here:
`<config directory>/custom_components/samsungctl_remote/`.

### Example configuration.yaml
```yaml
remote:
    - platform: samsungctl_remote
      name: samsung_tv
      file_path: "/config/sottosamctl.conf"
```

### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `samsungctl_remote` | `broadlink_asyncio`
**name (Required)** | Name your TV remote | `samsung_tv`
**file_path (Required)** | The path of samsungctl library configuration file. You will have to run the [library](https://github.com/kdschlosser/samsungctl) to get the configuration file. | `"/config/sottosamctl.conf"`

### Entities created

With the above configuration, the component will create and register an entity with id `remote.samsung_tv`.

### Sending commands
See [broadlink_asyncio](#broadlink_asyncio_commands). The supported commands can be found [here](https://github.com/kdschlosser/samsungctl/blob/master/samsungctl/key_mappings.py).
Examples of command list:

example| action
:--- | :---
`["ch345"]`| will send `KEY_3`, `KEY_4` and `KEY_5` in sequence
`["KEY_SOURCE#3"]`| will send `KEY_SOURCE`, three times
`["KEY_SOURCE","t1","KEY_LEFT","t0.5","KEY_LEFT"]`| will send `KEY_SOURCE`, wait 1s, send `KEY_LEFT`, wait 0.5s and send `KEY_LEFT`.


### Entity state and attributes

The state of the entities created by this component can take one of the following values:

value| meaning
:--- | :---
**on** | the TV is switched on
**off** | the TV is switched off

The remote entity does not provide attributes.

## upnp_renderingcontrol

RemoteDevice component that uses UPNP RenderingControl service to control volume, brightness, contrast, sharpness, muteness of a smart TV.
To get started put `/upnp_renderingcontrol/` here:
`<config directory>/custom_components/upnp_renderingcontrol/`.

### Example configuration.yaml
```yaml
remote:
    - platform: upnp_renderingcontrol
      name: samsung_tv_rc
      url: $upnp_url$
      timeout: 10
```

### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `upnp_renderingcontrol` | `upnp_renderingcontrol`
**name (Required)** | Name your device | `samsung_tv_rc`
**url (Required)** | The http URL of the RenderingControl service of the TV to control. | `http://192.168.25.44/tvrc.xml`
**timeout (Optional)** | Timeout in seconds used in the communication with your TV. **Default** `5` | `10`

To know if your TV supports UPNP RenderingControl service and its url, please take the following steps:

 1. run `pip3 install async-upnp-client`
 2. run `upnp-client --pprint search > search_upnp.txt`
 3. inspect the `search_upnp.txt` file searching for "RenderingControl". If your TV supports it, you will most likely find a section similar to this
```json
{
    "CACHE-CONTROL": "max-age=1800",
    "Date": "Thu, 01 Jan 1970 00:03:33 GMT",
    "EXT": "",
    "LOCATION": "http://192.168.25.53:7676/smp_15_",
    "SERVER": "SHP, UPnP/1.0, Samsung UPnP SDK/1.0",
    "ST": "urn:schemas-upnp-org:service:RenderingControl:1",
    "USN": "uuid:08f0d182-0096-1000-bf66-f877b8a47bf1::urn:schemas-upnp-org:service:RenderingControl:1",
    "Content-Length": "0",
    "_timestamp": "2019-05-09 01:35:19.611611",
    "_address": "192.168.25.53:50069",
    "_udn": "uuid:08f0d182-0096-1000-bf66-f877b8a47bf1",
    "_source": "search"
}
```
the string near to `LOCATION` is the url to place in the configuration file.

### Entities created

With the above configuration, the component will create and register an entity with id `remote.samsung_tv_rc`.

### Sending commands
See [broadlink_asyncio](#broadlink_asyncio_commands). The allowed commands are: 

 - `volume`
 - `contrast`
 - `brightness`
 - `sharpness`
 - `mute`
 
Please note that not all TVs support all commands.

Examples of command list:

example| action
:--- | :---| :---
`["volume#30"]` | will set the volume to 30%
`["volume#10","t1","brightness#100"]`| will set the volume to 10%, wait 1s and then set the brightness to 100%

### Entity state and attributes

The state of the entities created by this component can take one of the following values:

value| meaning
:--- | :---
**on** | the TV is switched on
**off** | the TV is switched off

The `attributes` dict of the entity created has the following fields:

key| value
:--- | :---
**volume** | the current volume of the TV.
**brightness** | the current brightness of the TV.
**contrast** | the current contrast of the TV.
**sharpness** | the current sharpness of the TV.
**mute** | the current mute state of the TV.

## upnp_maintvagent2

RemoteDevice component that uses UPNP MainTVAgent2 service  to set channel and video source of some Samsung smart TVs.
To get started put `/upnp_maintvagent2/` here:
`<config directory>/custom_components/upnp_maintvagent2/`.

### Example configuration.yaml
```yaml
remote:
    - platform: upnp_maintvagent2
      name: samsung_tv_mta2
      url: $upnp_url$
      timeout: 10
```

### Configuration variables

key | description| example
:--- | :---| :---
**platform (Required)** | **Must be** `upnp_maintvagent2` | `upnp_maintvagent2`
**name (Required)** | Name your device | `samsung_tv_mta2`
**url (Required)** | The http URL of the MainTVAgent2 service of the TV to control. | `http://192.168.25.44/tvmta2.xml`
**timeout (Optional)** | Timeout in seconds used in the communication with your TV. **Default** `5` | `10`

To know if your TV supports UPNP MainTVAgent2 service and its url, please take the following steps:

 1. run `pip3 install async-upnp-client`
 2. run `upnp-client --pprint search > search_upnp.txt`
 3. inspect the `search_upnp.txt` file searching for "MainTVAgent2". If your TV supports it you will most likely find a section similar to this
```json
{
    "CACHE-CONTROL": "max-age=1800",
    "Date": "Thu, 01 Jan 1970 00:03:33 GMT",
    "EXT": "",
    "LOCATION": "http://192.168.25.53:7676/smp_2_",
    "SERVER": "SHP, UPnP/1.0, Samsung UPnP SDK/1.0",
    "ST": "urn:samsung.com:service:MainTVAgent2:1",
    "USN": "uuid:05f5e100-0064-1000-b398-f877b8a47bf1::urn:samsung.com:service:MainTVAgent2:1",
    "Content-Length": "0",
    "_timestamp": "2019-05-09 01:35:19.619607",
    "_address": "192.168.25.53:45527",
    "_udn": "uuid:05f5e100-0064-1000-b398-f877b8a47bf1",
    "_source": "search"
}
```
the string near to `LOCATION` is the url to place in the configuration file.

### Entities created

With the above configuration, the component will create and register an entity with id `remote.samsung_tv_mta2`.

### Sending commands
See [broadlink_asyncio](#broadlink_asyncio_commands). The allowed commands are: 

 - `ch[0-9]+`
 - `sr#[0-9]+`

Examples of command list:

example| action
:--- | :---
`["ch340"]` | will set TV channel to 340
`["sr#1"]`| will set the AV source to the second one (HDMI1?) in the sources list. Usually the first one (index 0) is the TV source.


### Entity state and attributes

The state of the entities created by this component can take one of the following values:

value| meaning
:--- | :---
**on** | the TV is switched on
**off** | the TV is switched off

The `attributes` dict of the entity created has the following fields:

key| value
:--- | :---
**channell** | the number of the current channel set on the TV.
**source** | the name of the current source set on the TV.
**sourceidx** | the index of the current source set on the TV.

## google_assistant

A modified version of home-assistant [google-assistant component](https://www.home-assistant.io/components/google_assistant/) to support calling script that need parameters.

### Example configuration.yaml

```yaml
google_assistant:
    project_id: $google_project_id$
    api_key: $google_api_key$
    entity_config:
        script.remote_send_kkk_yellow:
            expose: true
            name: remote_send_kkk_yellow
            aliases:
                - giallo
                - tasto giallo
            data:
                key: KEY_YELLOW
                mult: 1
                var: samsung_tv
        script.remote_send_kkk_curtain:
            expose: true
            name: remote_send_kkk_curtain
            aliases:
                - curtain
            data_template: >
                {
                    "key": "{{ 'curtain_up' if on else 'curtain_down' }}",
                    "mult": 1,
                    "var": "diningroom"
                }
            onoff_template: 'on'
        script.remote_send_kkk_volume:
            expose: true
            name: remote_send_kkk_volume
            aliases:
                - volume
            data_template: >
                {
                    "key": "volume",
                    "mult": "{{variable}}",
                    "var": "samsung_tv_rc"
                }
            brightness_template: "{{states.remote.samsung_tv_rc.attributes.volume}}"

script:
    remote_send:
        sequence:
            - service: remote.send_command
              data_template:
                  entity_id: "remote.{{ var }}"
                  command: "{{ key }}#{{ mult }}"
```

### Configuration variables

Please refer to the original [google_assistant component](https://www.home-assistant.io/components/google_assistant/). This modified version allows to specify script entities in the `entity_config` with parameters. Instead of using script entity id in `entity_config` you can specify `script.myscript_kkk_par` where `par` is a name you can choose to identify the parameter passed to the script `myscript` and `_kkk_` is a fixed separator you *have to* use.
Script parameter can be specified by the `data` dict or the `data_template` dict. When using the original google_assistant component, the script invocation will always be seen as a scene that can be activated. When using the modified google_assistant component, the `data_template` field, the `onff_template` field and the `brightness_template` field, the script invocation will be seen by google as a light that can be switched on or off and whose brightness can be trimmed. `data_template` should expand to a valid dict in JSON format. This will be passed as `data` when invoking the script. Inside `data_template`, you can use the following variables:

variable | value
:--- | :---
**on** | `1` if a turn on action was invoked<br/>`0` if a turn off action was invoked<br/>`-1` if a brightness set action was invoked
**variable** | requested absolute brightness value if a brightness set action was invoked<br/>`-1` otherwise

To report to google the brightness and on/off state after the script invocation, `brightness_template` and `onoff_template` can be used. `brightness_template` has to return the actual absolute brightness value as string or int.  `onoff_template` has to return `"off"` to report the off state; anything else will report the on state.  Reporting to google the correct state is essential for the brightness set voice command to work properly.
