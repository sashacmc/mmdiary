# pylint: disable=global-statement,invalid-name

import logging
import requests

__get = requests.get
__post = requests.post
__put = requests.put
__delete = requests.delete
__head = requests.head
__options = requests.options

__proxy = None


def __add_proxy(kwargs):
    if __proxy is not None:
        kwargs['proxies'] = {"http": __proxy, "https": __proxy}
        logging.debug("Call with proxy %s", __proxy)


def get_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __get(*args, **kwargs)


def post_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __post(*args, **kwargs)


def put_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __put(*args, **kwargs)


def delete_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __delete(*args, **kwargs)


def head_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __head(*args, **kwargs)


def options_with_proxy(*args, **kwargs):
    __add_proxy(kwargs)
    return __get(*args, **kwargs)


requests.get = get_with_proxy
requests.post = post_with_proxy
requests.put = put_with_proxy
requests.delete = delete_with_proxy
requests.head = head_with_proxy
requests.options = options_with_proxy


def set_proxy(proxy):
    global __proxy
    __proxy = proxy
    if proxy is None:
        logging.info("Proxy disabled")
    else:
        logging.info("Proxy %s enabled", proxy)
