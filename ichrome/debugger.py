# -*- coding: utf-8 -*-
import asyncio
import atexit
import os
from functools import wraps
from inspect import isawaitable
from typing import Set

from torequests.utils import quote_plus

from .async_utils import AsyncChrome, AsyncTab
from .daemon import AsyncChromeDaemon, ChromeDaemon
from .exceptions import ChromeRuntimeError, ChromeValueError
from .logs import logger

__doc__ = r'''
>>> from ichrome.debugger import *
>>> daemon = launch()
INFO  2020-05-11 15:56:34 [ichrome] daemon.py(531): launch_chrome success: AsyncChromeDaemon(127.0.0.1:9222), args: "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir=C:\Users\ld\ichrome_user_data\chrome_9222 "--user-agent=Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36" --disable-gpu --no-first-run about:blank
>>> chrome = Chrome()
>>> tab: AsyncTab = chrome[0]
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
NameError: name 'AsyncTab' is not defined
>>> tab = chrome[0]
>>> tab.set_url('http://github.com', timeout=2)
{'id': 2, 'result': {'frameId': '1A832F05B3E57DFDBAD960FE502C3751', 'loaderId': 'DBA8653D3C9177074F787AF11562A249'}}
>>> tab.get_current_title()
'The world’s leading software development platform · GitHub'
>>> tab.get_current_url()
'https://github.com/'
>>> daemon.stop()
INFO  2020-05-11 15:57:08 [ichrome] daemon.py(396): AsyncChromeDaemon(127.0.0.1:9222) shutting down, start-up: 2020-05-11 15:56:32, duration: 35 seconds 724 ms.
INFO  2020-05-11 15:57:08 [ichrome] daemon.py(566): AsyncChromeDaemon(127.0.0.1:9222) daemon break after shutdown(2020-05-11 15:57:08).
INFO  2020-05-11 15:57:08 [ichrome] daemon.py(584): AsyncChromeDaemon(127.0.0.1:9222) daemon exited.
'''
__all__ = [
    'Chrome', 'Tab', 'Daemon', 'launch', 'AsyncTab', 'show_all_log',
    'mute_all_log', 'shutdown', 'get_a_tab', 'network_sniffer', 'crawl_once'
]


class SyncLoop:

    loop = asyncio.get_event_loop()

    def run_sync(self, future):
        return self.loop.run_until_complete(future)

    def wrap_sync(self, function):

        @wraps(function)
        def sync_func(*args, **kwargs):
            result = function(*args, **kwargs)
            if isawaitable(result):
                return self.run_sync(result)
            return result

        return sync_func

    def __getattr__(self, name):
        value = getattr(self._self, name)
        if callable(value):
            return self.wrap_sync(value)
        elif isawaitable(value):
            return self.run_sync(value)
        return value


def quit_while_daemon_missing(daemon):
    # quit the whole program while missing daemon process for daemon debugger
    if not daemon.get_proc(daemon.port):
        os._exit(1)


class Daemon(SyncLoop):
    daemons: Set['Daemon'] = set()

    def __init__(
        self,
        chrome_path=None,
        host="127.0.0.1",
        port=9222,
        headless=False,
        user_agent=None,
        proxy=None,
        user_data_dir=None,
        disable_image=False,
        start_url="about:blank",
        extra_config=None,
        max_deaths=1,
        daemon=True,
        block=False,
        timeout=1,
        debug=False,
        proc_check_interval=5,
        on_startup=None,
        on_shutdown=quit_while_daemon_missing,
    ):
        self._self = AsyncChromeDaemon(
            chrome_path=chrome_path,
            host=host,
            port=port,
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            user_data_dir=user_data_dir,
            disable_image=disable_image,
            start_url=start_url,
            extra_config=extra_config,
            max_deaths=max_deaths,
            daemon=daemon,
            block=block,
            timeout=timeout,
            debug=debug,
            proc_check_interval=proc_check_interval,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
        )
        self.run_sync(self._self.__aenter__())
        if not self.daemons:
            atexit.register(stop_all_daemons)
        self.daemons.add(self)
        self.running = True

    def stop(self):
        if self.running:
            return self.__exit__()
        self.running = False

    def __str__(self):
        return f"{self.__class__.__name__}({self._self.host}:{self._self.port})"

    def __repr__(self):
        return str(self)

    def __del__(self):
        self.stop()


class Chrome(SyncLoop):

    def __init__(self, host='127.0.0.1', port='9222', timeout=2, retry=1):
        self._self = AsyncChrome(host=host,
                                 port=port,
                                 timeout=timeout,
                                 retry=retry)
        ok = self.run_sync(self._self.connect())
        if not ok:
            raise ChromeRuntimeError(
                'remote debugging chrome not found, please launch a daemon at first like `python -m ichrome`'
            )

    def __getitem__(self, index: int):
        assert isinstance(index, int), 'only support int index'
        return self.get_tab(index=index)

    def get_tab(self, index=0):
        r = self.run_sync(self._self.get_server('/json'))
        rjsons = [rjson for rjson in r.json() if (rjson["type"] == "page")]
        if index is None:
            return [Tab(self, **rjson) for rjson in rjsons]
        else:
            return Tab(self, **rjsons[index])

    def get_tabs(self, filt_page_type: bool = True):
        return self.get_tab(None)

    def new_tab(self, url: str = ""):
        api = f'/json/new?{quote_plus(url)}'
        r = self.get_server(api)
        if r:
            rjson = r.json()
            tab = Tab(self, **rjson)
            tab._self._created_time = tab.now
            logger.debug(f"[new_tab] {tab._self} {rjson}")
            return tab
        else:
            return None

    def __del__(self):
        try:
            self.run_sync(self._self.__aexit__(None, None, None))
        except RuntimeError:
            # for running loop error
            pass

    def __str__(self):
        return f"{self.__class__.__name__}({self._self.host}:{self._self.port})"

    def __repr__(self):
        return str(self)


class Tab(SyncLoop):

    def __init__(self, chrome_debugger: Chrome, *args, **kwargs):
        kwargs['chrome'] = chrome_debugger._self
        self.chrome_debugger = chrome_debugger
        self._self = AsyncTab(*args, **kwargs)
        self.run_sync(self._self.connect().connect())

    def __del__(self):
        self._self.__del__()

    def __str__(self):
        return str(self._self)

    def __repr__(self):
        return str(self)


def launch(*args, **kwargs):
    return Daemon(*args, **kwargs)


def connect_a_chrome(host='127.0.0.1', port=None, **daemon_kwargs) -> Chrome:
    if not port:
        for port in ChromeDaemon.port_in_using:
            return Chrome(host=host, port=port)
        port = ChromeDaemon.get_free_port(host=host)
    try:
        return Chrome(host=host, port=port)
    except RuntimeError:
        # no existing port, launch a new chrome, and auto quit if chrome process missed.
        d = launch(host=host, port=port, **daemon_kwargs)
        return Chrome(host=host, port=d.port)


def get_a_tab(host='127.0.0.1', port=9222, **daemon_kwargs) -> AsyncTab:
    chrome = connect_a_chrome(host=host, port=port, **daemon_kwargs)
    return chrome.get_tab()


def get_a_new_tab(host='127.0.0.1', port=9222, **daemon_kwargs) -> AsyncTab:
    chrome = connect_a_chrome(host=host, port=port, **daemon_kwargs)
    return chrome.new_tab()


def show_all_log():
    AsyncTab._log_all_recv = True
    logger.setLevel(1)


def mute_all_log():
    AsyncTab._log_all_recv = False
    logger.setLevel(60)


def stop_all_daemons():
    if Daemon.daemons:
        logger.debug(f'auto shutdown {Daemon.daemons}')
        for daemon in Daemon.daemons:
            daemon.stop()


def shutdown():
    stop_all_daemons()
    os._exit(0)


def network_sniffer(timeout=60, filter_function=None, callback_function=None):
    import json

    get_data_value = AsyncTab.get_data_value

    def _filter_function(r):
        req = json.dumps(get_data_value(r, 'params.request'),
                         ensure_ascii=0,
                         indent=2)
        req_type = get_data_value(r, 'params.type')
        doc_url = get_data_value(r, 'params.documentURL')
        print(f'{doc_url} - {req_type}\n{req}', end=f'\n{"="*40}\n', flush=True)

    # listen network flow in 60 s
    timeout = timeout
    tab = get_a_tab()
    filter_function = filter_function or _filter_function
    callback_function = callback_function or (lambda r: print(r))
    tab.wait_request(filter_function=filter_function,
                     timeout=timeout,
                     callback_function=callback_function)


async def crawl_once(**kwargs):
    url = kwargs.pop('start_url', None)
    if not url:
        raise ChromeValueError('Can not crawl with null start_url')
    async with AsyncChromeDaemon(**kwargs) as cd:
        async with AsyncChrome(
                host=kwargs.get('host', '127.0.0.1'),
                port=cd.port,
                timeout=cd._timeout or 2,
        ) as chrome:
            async with chrome.connect_tab(0, auto_close=True) as tab:
                await tab.set_url(url, timeout=cd._timeout)
                html = await tab.get_html(timeout=cd._timeout)
                return html


async def clear_cache_handler(**kwargs):
    async with AsyncChromeDaemon(**kwargs) as cd:
        async with AsyncChrome(
                host=kwargs.get('host', '127.0.0.1'),
                port=kwargs.get('port', 9222),
                timeout=cd._timeout or 2,
        ) as chrome:
            async with chrome.connect_tab(0, auto_close=True) as tab:
                await tab.clear_browser_cache()
