'''
Created on 10 mag 2019

@author: Matteo
'''
from .const import ORVIBO_ASYNCIO_DATA_KEY


def get_orvibo_class(hassdata, classname):
    if ORVIBO_ASYNCIO_DATA_KEY not in hassdata or classname not in hassdata[ORVIBO_ASYNCIO_DATA_KEY]:
        from asyncio_orvibo.allone import AllOne
        from asyncio_orvibo.s20 import S20
        from asyncio_orvibo.orvibo_udp import PORT
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.info("Initializing orvibo_asyncio classes")
        hassdata[ORVIBO_ASYNCIO_DATA_KEY] = dict(AllOne=AllOne, S20=S20, PORT=PORT)
    return hassdata[ORVIBO_ASYNCIO_DATA_KEY][classname]
