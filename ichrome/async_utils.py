# -*- coding: utf-8 -*-
# fast and stable connection
import asyncio
import inspect
import json
import re
import sys
import time
from asyncio.base_futures import _PENDING
from asyncio.futures import Future
from base64 import b64decode, b64encode
from fnmatch import fnmatchcase
from pathlib import Path
from typing import (Any, Awaitable, Callable, Coroutine, Dict, List, Optional,
                    Set, Union)
from weakref import WeakValueDictionary

from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.aiohttp_dummy import Requests
from torequests.dummy import NewResponse, _exhaust_simple_coro
from torequests.utils import UA, quote_plus, urljoin

from .base import (INF, NotSet, Tag, TagNotFound, async_run,
                   clear_chrome_process, ensure_awaitable, get_memory_by_port)
from .exceptions import (ChromeRuntimeError, ChromeTypeError, ChromeValueError,
                         TabConnectionError)
from .logs import logger


async def _ensure_awaitable_callback_result(callback_function, result):
    if callback_function and callable(callback_function):
        callback_result = callback_function(result)
    else:
        return result
    if inspect.isawaitable(callback_result):
        return await callback_result
    else:
        return callback_result


class _TabConnectionManager:

    def __init__(self, tabs):
        self.tabs = tabs
        self.ws_connections = set()

    async def __aenter__(self) -> None:
        for tab in self.tabs:
            ws_connection = tab()
            await ws_connection.__aenter__()
            self.ws_connections.add(ws_connection)

    async def __aexit__(self, *args):
        for ws_connection in self.ws_connections:
            if not ws_connection._closed:
                await ws_connection.__aexit__(None, None, None)


class _SingleTabConnectionManager:

    def __init__(self,
                 chrome: 'AsyncChrome',
                 index: Union[None, int, str] = 0,
                 auto_close: bool = False,
                 target_kwargs: dict = None,
                 flatten: bool = None):
        self.chrome = chrome
        self.index = index
        self.tab: 'AsyncTab' = None
        self.target_kwargs: dict = target_kwargs
        self._auto_close = auto_close
        self.flatten = AsyncTab._DEFAULT_FLATTEN if flatten is None else flatten

    async def __aenter__(self) -> 'AsyncTab':
        if self.target_kwargs:
            data = await self.chrome.browser.send('Target.createTarget',
                                                  kwargs=self.target_kwargs)
            tab_id = data['result']['targetId']
            self.tab = await self.chrome.get_tab(tab_id)
        elif isinstance(self.index, int):
            self.tab = await self.chrome.get_tab(self.index)
        elif isinstance(self.index, str) and '://' not in self.index:
            # tab_id
            self.tab = await self.chrome.get_tab(self.index)
        else:
            self.tab = await self.chrome.new_tab(self.index or "")
        if not self.tab:
            raise ChromeRuntimeError(
                f'Tab init failed. index={self.index}, chrome={self.chrome}')
        if self.flatten:
            self.tab.set_flatten()
        await self.tab.ws_connection.__aenter__()
        return self.tab

    async def __aexit__(self, *args):
        if self.tab:
            await self.tab.ws_connection.__aexit__()
            if self._auto_close:
                await self.tab.close_tab()


class _SingleTabConnectionManagerDaemon(_SingleTabConnectionManager):
    # deprecated
    def __init__(self,
                 host,
                 port,
                 index: Union[None, int, str] = 0,
                 auto_close: bool = False,
                 timeout: int = None,
                 flatten: bool = False):
        self.chrome = AsyncChrome(host=host, port=port, timeout=timeout)
        super().__init__(chrome=self.chrome,
                         index=index,
                         auto_close=auto_close,
                         flatten=flatten)

    async def __aenter__(self) -> 'AsyncTab':
        await self.chrome.__aenter__()
        return await super().__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.chrome.__aexit__(*args)


class _WSConnection:

    def __init__(self, tab):
        self.tab = tab
        self._closed = None
        self._recv_task: Future = None

    def __str__(self):
        return f'<{self.__class__.__name__}: {None if self._closed is None else not self._closed}>'

    @property
    def connected(self):
        return not self._closed

    @property
    def browser(self):
        return self.tab.chrome.browser

    async def __aenter__(self) -> 'AsyncTab':
        return await self.connect()

    async def connect(self) -> 'AsyncTab':
        """Connect to websocket, and set tab.ws as aiohttp.client_ws.ClientWebSocketResponse."""
        if self.tab.flatten:
            data = await self.browser.send('Target.attachToTarget',
                                           targetId=self.tab.tab_id,
                                           flatten=True)
            self.tab._session_id = data['result']['sessionId']
            self.browser._sessions[self.tab._session_id] = self.tab
        else:
            for _ in range(3):
                try:
                    self.tab.ws = await self.tab.req.session.ws_connect(
                        self.tab.webSocketDebuggerUrl, **self.tab.ws_kwargs)
                    logger.debug(
                        f'[connected] {self.tab} websocket connection created.')
                    break
                except (ClientError, WebSocketError) as err:
                    # tab missing(closed)
                    logger.error(
                        f'[missing] {self.tab} missing ws connection. {err}')
            else:
                raise TabConnectionError(f'Connect to tab failed, {self.tab}')
            # start the daemon background.
            await self._start_tasks()
        return self.tab

    async def _heartbeat_daemon(self):
        while not self.tab.ws.closed:
            await asyncio.sleep(self.tab.heartbeat)
        raise KeyboardInterrupt(
            f'Tab missed connection before closed, {self.tab}')

    async def _start_tasks(self):
        if not self.tab.flatten:
            self._recv_task = asyncio.ensure_future(self.tab._recv_daemon())

    async def _stop_tasks(self):
        if self._recv_task and not self._recv_task.done():
            try:
                await asyncio.wait_for(self._recv_task, timeout=0.1)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self):
        if self._closed:
            return
        # stop daemon if shutdown
        if self.tab.flatten:
            self._closed = True
            if self.tab._session_id:
                self.tab._session_id = None
                try:
                    await self.browser.send('Target.detachFromTarget',
                                            sessionId=self.tab._session_id)
                except ChromeRuntimeError as error:
                    if 'ws has been closed' not in str(error):
                        raise error
                finally:
                    self.browser._sessions.pop(self.tab._session_id, None)
        else:
            await self._stop_tasks()
            if self.tab.ws:
                if not self.tab.ws.closed:
                    await self.tab.ws.close()
                self._closed = self.tab.ws.closed
                self.tab.ws = None
            else:
                self._closed = True

    async def __aexit__(self, *args):
        await self.shutdown()

    def __del__(self):
        logger.debug(
            f'[disconnected] {self.tab!r} ws_connection closed[{self._closed}]')


class GetValueMixin:
    '''Get value with path'''

    @staticmethod
    def get_data_value(item,
                       value_path: str = 'result.result.value',
                       default=None):
        """default value_path is for js response dict"""
        if not item:
            return default
        if not value_path:
            return item
        try:
            for key in value_path.split('.'):
                item = item.__getitem__(key)
            return item
        except (KeyError, TypeError):
            return default

    @classmethod
    def check_error(cls, name, result, value_path='error.message', **kwargs):
        error = cls.get_data_value(result, value_path=value_path)
        if error:
            logger.info(f'{name} failed: {kwargs}. result: {result}')
        return not error


class AsyncTab(GetValueMixin):
    """Tab operations in async environment.

        The timeout variable -- wait for the events::

            NotSet:
                using the self.timeout by default
            None:
                using the self._MAX_WAIT_TIMEOUT instead, default to float('inf')
            0:
                no wait
            int / float:
                wait `timeout` seconds
"""
    _log_all_recv = False
    _min_move_interval = 0.05
    # only enable without Params
    _domains_can_be_enabled = {
        'Accessibility', 'Animation', 'ApplicationCache', 'Audits', 'CSS',
        'Cast', 'DOM', 'DOMSnapshot', 'DOMStorage', 'Database',
        'HeadlessExperimental', 'IndexedDB', 'Inspector', 'LayerTree', 'Log',
        'Network', 'Overlay', 'Page', 'Performance', 'Security',
        'ServiceWorker', 'WebAudio', 'WebAuthn', 'Media', 'Console', 'Debugger',
        'HeapProfiler', 'Profiler', 'Runtime'
    }
    # timeout for recv, for wait_XXX methods
    # You can reset this with float instead of forever, like 30 * 60
    _MAX_WAIT_TIMEOUT = float('inf')
    # timeout for recv, not for wait_XXX methods
    _DEFAULT_RECV_TIMEOUT = 5.0
    # aiohttp ws timeout default to 10.0, here is 5
    _DEFAULT_CONNECT_TIMEOUT = 5.0
    _RECV_DAEMON_BREAK_CALLBACK = None
    # default max_msg_size has been set to 20MB, for 4MB is too small.
    _DEFAULT_WS_KWARGS: Dict = {"max_msg_size": 20 * 1024**2}
    # default flatten arg
    _DEFAULT_FLATTEN = True

    def __init__(self,
                 tab_id: str = None,
                 title: str = None,
                 url: str = None,
                 type: str = None,
                 description: str = None,
                 webSocketDebuggerUrl: str = None,
                 devtoolsFrontendUrl: str = None,
                 json: str = None,
                 chrome: 'AsyncChrome' = None,
                 timeout=NotSet,
                 ws_kwargs: dict = None,
                 default_recv_callback: Callable = None,
                 _recv_daemon_break_callback: Callable = None,
                 flatten: bool = None,
                 **kwargs):
        """Init AsyncTab instance.

        original Tab JSON::

            [{
                "description": "",
                "devtoolsFrontendUrl": "/devtools/inspector.html?ws=localhost:9222/devtools/page/8ED4BDD54713572BCE026393A0137214",
                "id": "8ED4BDD54713572BCE026393A0137214",
                "title": "about:blank",
                "type": "page",
                "url": "http://localhost:9222/json",
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/8ED4BDD54713572BCE026393A0137214"
            }]

        Args:
            tab_id (str, optional): defaults to kwargs.pop('id').
            title (str, optional): tab title. Defaults to None.
            url (str, optional): tab url, binded to self._url. Defaults to None.
            type (str, optional): tab type, often be `page` type. Defaults to None.
            description (str, optional): tab description. Defaults to None.
            webSocketDebuggerUrl (str, optional): ws URL to connect. Defaults to None.
            devtoolsFrontendUrl (str, optional): devtools UI URL. Defaults to None.
            json (str, optional): raw Tab JSON. Defaults to None.
            chrome (AsyncChrome, optional): the AsyncChrome object which the Tab belongs to. Defaults to None.
            timeout (_type_, optional): default recv timeout, defaults to AsyncTab._DEFAULT_RECV_TIMEOUT. Defaults to NotSet.
            ws_kwargs (dict, optional): kwargs for ws connection. Defaults to AsyncTab._DEFAULT_WS_KWARGS.
            default_recv_callback (Callable, optional): called for each data received, sync/async function only accept 1 arg of data comes from ws recv. Defaults to None.
            _recv_daemon_break_callback (Callable, optional): like the tab_close_callback. sync/async function only accept 1 arg of self while _recv_daemon break. defaults to None.
            flatten (bool, optional): use flatten mode with sessionId. Defaults to AsyncTab._DEFAULT_FLATTEN.

        """

        tab_id = tab_id or kwargs.pop('id')
        if not tab_id:
            raise ChromeValueError(f'tab_id should not be null, {tab_id}')
        self.tab_id = tab_id
        self._title = title
        self._url = url
        self.type = type
        self.description = description
        self.devtoolsFrontendUrl = devtoolsFrontendUrl
        if tab_id and not webSocketDebuggerUrl:
            _chrome_port_str = f':{chrome.port}' if chrome.port else ''
            webSocketDebuggerUrl = f'ws://{chrome.host}{_chrome_port_str}/devtools/page/{tab_id}'
        self.webSocketDebuggerUrl = webSocketDebuggerUrl
        self.json = json
        self.chrome = chrome
        self.timeout = self._DEFAULT_RECV_TIMEOUT if timeout is NotSet else timeout
        self.ws_kwargs = ws_kwargs or self._DEFAULT_WS_KWARGS
        self.ws_kwargs.setdefault('timeout', self._DEFAULT_CONNECT_TIMEOUT)
        self.ws = None
        self.ws_connection: _WSConnection = _WSConnection(self)
        if self.chrome:
            self.req = self.chrome.req
        else:
            self.req = Requests()
        # using default_recv_callback.setter, default_recv_callback can be list or function
        self.default_recv_callback = default_recv_callback
        # alias of methods
        self.mouse_click_tag = self.mouse_click_element_rect
        self.clear_cookies = self.clear_browser_cookies
        self.inject_js = self.inject_js_url
        self.get_bounding_client_rect = self.get_element_clip
        # internal variables
        self._created_time = int(time.time())
        self._message_id = 0
        self._recv_daemon_break_callback = _recv_daemon_break_callback or self._RECV_DAEMON_BREAK_CALLBACK
        self._closed = False
        self._listener = Listener()
        self._buffers: WeakValueDictionary = WeakValueDictionary()
        self._enabled_domains: Set[str] = set()
        self._default_recv_callback: List[Callable] = []
        self._sessions: WeakValueDictionary = WeakValueDictionary()
        self._session_id: str = None
        # sessions for flatten mode
        self.flatten = self._DEFAULT_FLATTEN if flatten is None else flatten
        if self.flatten:
            self.set_flatten()

    async def close_browser(self, timeout=0):
        return await self.send('Browser.close', timeout=timeout)

    @property
    def url(self) -> Awaitable[str]:
        """Return the current url, `await tab.url`."""
        return self.get_current_url()

    async def refresh_tab_info(self) -> bool:
        "refresh the tab meta info with tab_id from /json"
        r = await self.chrome.get_server('/json')
        if r:
            for tab_info in r.json():
                if tab_info['id'] == self.tab_id:
                    self._title = tab_info['title']
                    self.description = tab_info['description']
                    self.type = tab_info['type']
                    self._url = tab_info['url']
                    self.json = tab_info
                    return True
        return False

    async def activate_tab(self) -> Union[str, bool]:
        """activate tab with chrome http endpoint"""
        return await self.chrome.activate_tab(self)

    async def close_tab(self) -> Union[str, bool]:
        """close tab with chrome http endpoint"""
        return await self.chrome.close_tab(self)

    async def activate(self, timeout=NotSet) -> Union[dict, None]:
        """[Page.bringToFront], activate tab with cdp websocket"""
        return await self.send("Page.bringToFront", timeout=timeout)

    async def close(self, timeout=0) -> Union[dict, None]:
        """[Page.close], close tab with cdp websocket. will lose ws, so timeout default to 0."""
        try:
            return await self.send("Page.close", timeout=timeout)
        except ChromeRuntimeError as error:
            logger.error(f'close tab failed for {error!r}')
            return None

    async def crash(self, timeout=0) -> Union[dict, None]:
        """[Page.crash], will lose ws, so timeout default to 0."""
        return await self.send("Page.crash", timeout=timeout)

    async def send(self,
                   method: str,
                   timeout=NotSet,
                   callback_function: Optional[Callable] = None,
                   kwargs: Dict[str, Any] = None,
                   auto_enable=True,
                   force=None,
                   **_kwargs) -> Union[None, dict]:
        '''Send message to Tab. callback_function only work whlie timeout!=0.
        If timeout is not None: wait for recv event.
        If auto_enable: will check the domain enabled automatically.
        If callback_function: run while received the response msg.

        the `force` arg is deprecated, use auto_enable instead.
        '''
        timeout = self.ensure_timeout(timeout)
        if kwargs:
            _kwargs.update(kwargs)
        request = {"id": self.msg_id, "method": method, "params": _kwargs}
        if self._session_id:
            request['sessionId'] = self._session_id
        try:
            if not self.ws or self.ws.closed:
                raise ChromeRuntimeError(f'[closed] {self} ws has been closed')
            if auto_enable or force is False:
                await self.auto_enable(method, timeout=timeout)
            logger.debug(f"[send] {self!r} {request}")
            if timeout != 0:
                # wait for msg filted by id
                event = {"id": request["id"]}
                f = self.recv(event,
                              timeout=timeout,
                              callback_function=callback_function)
                await self.ws.send_json(request)
                return await f
            else:
                # timeout == 0, no need wait for response.
                return await self.ws.send_json(request)
        except (ClientError, WebSocketError, TypeError) as err:
            err_msg = f'{self} [send] msg {request} failed for {err}'
            logger.error(err_msg)
            raise ChromeRuntimeError(err_msg)

    def recv(
        self,
        event_dict: dict,
        timeout=NotSet,
        callback_function: Callable = None,
    ) -> Awaitable[Union[dict, None]]:
        """Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.

        Args:
            event_dict (dict):  dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
            timeout (_type_, optional): await seconds, None for self._MAX_WAIT_TIMEOUT, 0 for 0 seconds.. Defaults to NotSet.
            callback_function (_type_, optional): event callback_function function accept only one arg(the event dict).. Defaults to None.

        Returns:
            Awaitable[Union[dict, None]]: the event dict from websocket recv
        """

        timeout = self.ensure_timeout(timeout)
        if isinstance(timeout, (float, int)) and timeout <= 0:
            # no wait
            return None
        if self._session_id:
            event_dict['sessionId'] = self._session_id
        return self._recv(event_dict=event_dict,
                          timeout=timeout,
                          callback_function=callback_function)

    async def enable(self,
                     domain: str,
                     force: bool = False,
                     timeout=None,
                     kwargs: dict = None,
                     **_kwargs):
        '''domain: Network or Page and so on, will send `{domain}.enable`. Automatically check for duplicated sendings if not force.'''
        if not force:
            # no need for duplicated enable.
            if domain not in self._domains_can_be_enabled or domain in self._enabled_domains:
                return True
        if kwargs:
            _kwargs.update(kwargs)
        # enable timeout should not be 0
        if timeout == 0:
            timeout = self.timeout
        result = await self.send(f'{domain}.enable',
                                 timeout=timeout,
                                 auto_enable=False,
                                 kwargs=_kwargs)
        if result is not None:
            self._enabled_domains.add(domain)
        return result

    async def disable(self, domain: str, force: bool = False, timeout=NotSet):
        '''domain: Network / Page and so on, will send `domain.disable`. Automatically check for duplicated sendings if not force.'''
        if not force:
            # no need for duplicated enable.
            if domain in self._domains_can_be_enabled or domain not in self._enabled_domains:
                return True
        result = await self.send(f'{domain}.disable',
                                 timeout=timeout,
                                 auto_enable=False)
        if result is not None:
            self._enabled_domains.discard(domain)
        return result

    async def get_all_cookies(self, timeout=NotSet):
        """[Network.getAllCookies], return all the cookies of this browser."""
        # {'id': 12, 'result': {'cookies': [{'name': 'test2', 'value': 'test_value', 'domain': 'python.org', 'path': '/', 'expires': -1, 'size': 15, 'httpOnly': False, 'secure': False, 'session': True}]}}
        result = await self.send("Network.getAllCookies", timeout=timeout)
        return self.get_data_value(result, 'result.cookies')

    async def clear_browser_cookies(self, timeout=NotSet):
        """[Network.clearBrowserCookies]"""
        return await self.send("Network.clearBrowserCookies", timeout=timeout)

    async def clear_browser_cache(self, timeout=NotSet):
        """[Network.clearBrowserCache]"""
        return await self.send("Network.clearBrowserCache", timeout=timeout)

    async def delete_cookies(self,
                             name: str,
                             url: Optional[str] = '',
                             domain: Optional[str] = '',
                             path: Optional[str] = '',
                             timeout=NotSet):
        """[Network.deleteCookies], deleteCookies by name, with url / domain / path."""
        if not any((url, domain)):
            raise ChromeValueError('URL and domain should not be both null.')
        return await self.send("Network.deleteCookies",
                               name=name,
                               url=url,
                               domain=domain,
                               path=path,
                               timeout=timeout)

    async def get_cookies(self,
                          urls: Union[List[str], str] = None,
                          timeout=NotSet) -> List:
        """[Network.getCookies], get cookies of urls."""
        if urls:
            if isinstance(urls, str):
                urls = [urls]
            urls = list(urls)
            result = await self.send("Network.getCookies",
                                     urls=urls,
                                     timeout=timeout)
        else:
            result = await self.send("Network.getCookies", timeout=timeout)
        return self.get_data_value(result, 'result.cookies', [])

    async def set_cookies(self,
                          cookies: List,
                          ensure_keys=False,
                          timeout=NotSet):
        """[Network.setCookies]"""
        for cookie in cookies:
            if not ('url' in cookie or 'domain' in cookie):
                raise ChromeValueError(
                    'URL and domain should not be both null.')
        if ensure_keys:
            valid_keys = {
                'name', 'value', 'url', 'domain', 'path', 'secure', 'httpOnly',
                'sameSite', 'expires', 'priority'
            }
            cookies = [{k: v
                        for k, v in cookie.items()
                        if k in valid_keys}
                       for cookie in cookies]
        return await self.send("Network.setCookies",
                               cookies=cookies,
                               timeout=timeout)

    async def set_cookie(self,
                         name: str,
                         value: str,
                         url: Optional[str] = '',
                         domain: Optional[str] = '',
                         path: Optional[str] = '',
                         secure: Optional[bool] = False,
                         httpOnly: Optional[bool] = False,
                         sameSite: Optional[str] = '',
                         expires: Optional[int] = None,
                         timeout=NotSet,
                         **_):
        """[Network.setCookie]
name [string] Cookie name.
value [string] Cookie value.
url [string] The request-URI to associate with the setting of the cookie. This value can affect the default domain and path values of the created cookie.
domain [string] Cookie domain.
path [string] Cookie path.
secure [boolean] True if cookie is secure.
httpOnly [boolean] True if cookie is http-only.
sameSite [CookieSameSite] Cookie SameSite type.
expires [TimeSinceEpoch] Cookie expiration date, session cookie if not set"""
        if not any((url, domain)):
            raise ChromeValueError('URL and domain should not be both null.')
        kwargs: Dict[str, Any] = dict(name=name,
                                      value=value,
                                      url=url,
                                      domain=domain,
                                      path=path,
                                      secure=secure,
                                      httpOnly=httpOnly,
                                      sameSite=sameSite,
                                      expires=expires)
        kwargs = {
            key: value for key, value in kwargs.items() if value is not None
        }
        return await self.send("Network.setCookie",
                               timeout=timeout,
                               callback_function=None,
                               **kwargs)

    async def get_current_url(self, timeout=NotSet) -> str:
        "JS: window.location.href"
        url = await self.get_variable("window.location.href", timeout=timeout)
        return url or ""

    async def get_current_title(self, timeout=NotSet) -> str:
        "JS: document.title"
        title = await self.get_variable("document.title", timeout=timeout)
        return title or ""

    @property
    def current_title(self) -> Awaitable[str]:
        return self.get_current_title()

    @property
    def title(self) -> Awaitable[str]:
        "await tab.title"
        return self.get_current_title()

    @property
    def current_html(self) -> Awaitable[str]:
        return self.html

    async def get_html(self, timeout=NotSet) -> str:
        """return html from `document.documentElement.outerHTML`"""
        html = await self.get_variable('document.documentElement.outerHTML',
                                       timeout=timeout)
        return html or ""

    @property
    def html(self) -> Awaitable[str]:
        """`await tab.html`. return html from `document.documentElement.outerHTML`"""
        return self.get_html()

    async def set_html(self, html: str, frame_id: str = None, timeout=NotSet):
        "JS: document.write, or Page.setDocumentContent if given frame_id"
        if frame_id is None:
            frame_id = await self.get_page_frame_id(timeout=timeout)
        if frame_id is None:
            return await self.js(f'document.write(`{html}`)', timeout=timeout)
        else:
            return await self.send('Page.setDocumentContent',
                                   html=html,
                                   frameId=frame_id,
                                   timeout=timeout)

    async def get_page_frame_id(self, timeout=NotSet):
        "get frame id of current page"
        result = await self.get_frame_tree(timeout=timeout)
        return self.get_data_value(result,
                                   value_path='result.frameTree.frame.id')

    @property
    def frame_tree(self):
        return self.get_frame_tree()

    async def get_frame_tree(self, timeout=NotSet):
        "[Page.getFrameTree], get current page frame tree"
        return await self.send('Page.getFrameTree', timeout=timeout)

    async def stop_loading_page(self, timeout=0):
        '''[Page.stopLoading]'''
        return await self.send("Page.stopLoading", timeout=timeout)

    async def wait_loading(self,
                           timeout=None,
                           callback_function: Optional[Callable] = None,
                           timeout_stop_loading=False) -> bool:
        '''wait Page.loadEventFired event while page loaded.
        If page loaded event catched, return True.
        WARNING: methods with prefix `wait_` the `timeout` default to None.
        '''
        if timeout == 0:
            return False
        data = await self.wait_event("Page.loadEventFired",
                                     timeout=timeout,
                                     callback_function=callback_function)
        if data is None and timeout_stop_loading:
            await self.stop_loading_page()
            return False
        return bool(data)

    async def wait_page_loading(self,
                                timeout=None,
                                callback_function: Optional[Callable] = None,
                                timeout_stop_loading=False):
        return await self.wait_loading(
            timeout=timeout,
            callback_function=callback_function,
            timeout_stop_loading=timeout_stop_loading)

    async def wait_event(
            self,
            event_name: str,
            timeout=None,
            callback_function: Optional[Callable] = None,
            filter_function: Optional[Callable] = None
    ) -> Union[dict, None, Any]:
        """Similar to self.recv, but has the filter_function to distinct duplicated method of event.
        WARNING: the `timeout` default to None when methods with prefix `wait_`
        """
        timeout = self.ensure_timeout(timeout)
        start_time = time.time()
        result = None
        event = {"method": event_name}
        while 1:
            if timeout is not None:
                # update the real timeout
                timeout = timeout - (time.time() - start_time)
                if timeout < 0:
                    break
            # avoid same method but different event occured, use filter_function
            _result = await self.recv(event, timeout=timeout)
            if _result is None:
                continue
            if filter_function:
                try:
                    ok = await _ensure_awaitable_callback_result(
                        filter_function, _result)
                    if ok:
                        result = _result
                        break
                except Exception as error:
                    logger.error(f'wait_event crashed for: {error!r}')
                    raise error
            elif _result:
                result = _result
                break
        return await _ensure_awaitable_callback_result(callback_function,
                                                       result)

    async def wait_console(
            self,
            timeout=None,
            callback_function: Optional[Callable] = None,
            filter_function: Optional[Callable] = None) -> Union[None, dict]:
        """Wait the filted Runtime.consoleAPICalled event.

        consoleAPICalled event types:
        log, debug, info, error, warning, dir, dirxml, table, trace, clear, startGroup, startGroupCollapsed, endGroup, assert, profile, profileEnd, count, timeEnd

        return dict or None like:
        {'method':'Runtime.consoleAPICalled','params': {'type':'log','args': [{'type':'string','value':'123'}],'executionContextId':13,'timestamp':1592895800590.75,'stackTrace': {'callFrames': [{'functionName':'','scriptId':'344','url':'','lineNumber':0,'columnNumber':8}]}}}
"""
        return await self.wait_event('Runtime.consoleAPICalled',
                                     timeout=timeout,
                                     callback_function=callback_function,
                                     filter_function=filter_function)

    async def wait_console_value(self,
                                 timeout=None,
                                 callback_function: Optional[Callable] = None,
                                 filter_function: Optional[Callable] = None):
        """Wait the Runtime.consoleAPICalled event, simple data type (null, number, Boolean, string) will try to get value and return.

        This may be very useful for send message from Chrome to Python programs with a JSON string.

        {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'boolean', 'value': True}], 'executionContextId': 4, 'timestamp': 1592924155017.107, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '343', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
        {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'object', 'subtype': 'null', 'value': None}], 'executionContextId': 4, 'timestamp': 1592924167384.516, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '362', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
        {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'number', 'value': 1, 'description': '1234'}], 'executionContextId': 4, 'timestamp': 1592924176778.166, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '385', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
        {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'string', 'value': 'string'}], 'executionContextId': 4, 'timestamp': 1592924187756.2349, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '404', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
        """
        result = await self.wait_event('Runtime.consoleAPICalled',
                                       timeout=timeout,
                                       filter_function=filter_function)
        try:
            result = result['params']['args'][0]['value']
        except (IndexError, KeyError, TypeError):
            pass
        return await _ensure_awaitable_callback_result(callback_function,
                                                       result)

    def wait_response_context(self,
                              filter_function: Optional[Callable] = None,
                              callback_function: Optional[Callable] = None,
                              response_body: bool = True,
                              timeout=NotSet):
        """
        Handler context for tab.wait_response.

            async with tab.wait_response_context(
                        filter_function=lambda r: tab.get_data_value(
                            r, 'params.response.url') == 'http://httpbin.org/get',
                        timeout=5,
                ) as r:
                    await tab.goto('http://httpbin.org/get')
                    result = await r
                    if result:
                        print(result['data'])
        """
        return WaitContext(
            self.wait_response(
                filter_function=filter_function,
                callback_function=callback_function,
                response_body=response_body,
                timeout=timeout,
            ))

    async def wait_response(self,
                            filter_function: Optional[Callable] = None,
                            callback_function: Optional[Callable] = None,
                            response_body: bool = True,
                            timeout=NotSet):
        '''wait a special response filted by function, then run the callback_function.

        Sometimes the request fails to be sent, so use the `tab.wait_request` instead.
        if response_body:
            the non-null request_dict will contains response body.'''
        timeout = self.ensure_timeout(timeout)
        start_time = time.time()
        request_dict = await self.wait_event("Network.responseReceived",
                                             filter_function=filter_function,
                                             timeout=timeout)
        if timeout is not None:
            timeout = timeout - (time.time() - start_time)
        if response_body:
            # set the data value
            if request_dict:
                data = await self.get_response_body(
                    request_dict['params']['requestId'],
                    timeout=timeout,
                    wait_loading=True)
                request_dict['data'] = data
            elif isinstance(request_dict, dict):
                request_dict['data'] = None
        return await _ensure_awaitable_callback_result(callback_function,
                                                       request_dict)

    async def wait_request(self,
                           filter_function: Optional[Callable] = None,
                           callback_function: Optional[Callable] = None,
                           timeout=None):
        '''Network.requestWillBeSent. To wait a special request filted by function, then run the callback_function(request_dict).

        Often used for HTTP packet capture:

            `await tab.wait_request(filter_function=lambda r: print(r), timeout=10)`

        WARNING: requestWillBeSent event fired do not mean the response is ready,
        should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
        WARNING: methods with prefix `wait_` the `timeout` default to None.
'''
        request_dict = await self.wait_event("Network.requestWillBeSent",
                                             filter_function=filter_function,
                                             timeout=timeout)
        return await _ensure_awaitable_callback_result(callback_function,
                                                       request_dict)

    async def wait_request_loading(self,
                                   request_dict: Union[None, dict, str],
                                   timeout=None):
        "wait for the Network.loadingFinished event of given request id"

        def request_id_filter(event):
            if event:
                return event["params"]["requestId"] == request_id

        request_id = self._ensure_request_id(request_dict)
        return await self.wait_event('Network.loadingFinished',
                                     timeout=timeout,
                                     filter_function=request_id_filter)

    async def wait_loading_finished(self, request_dict: dict, timeout=None):
        "wait for the Network.loadingFinished event of given request id"
        return await self.wait_request_loading(request_dict=request_dict,
                                               timeout=timeout)

    def iter_events(self,
                    events: List[str],
                    timeout: Union[float, int] = None,
                    maxsize=0,
                    kwargs: Any = None,
                    callback: Callable = None) -> 'EventBuffer':
        """Iter events with a async context.
        ::

            async with AsyncChromeDaemon() as cd:
                async with cd.connect_tab() as tab:
                    async with tab.iter_events(['Page.loadEventFired'],
                                            timeout=60) as e:
                        await tab.goto('http://httpbin.org/get')
                        print(await e)
                        # {'method': 'Page.loadEventFired', 'params': {'timestamp': 1380679.967344}}
                        # await tab.goto('http://httpbin.org/get')
                        # print(await e.get())
                        # # {'method': 'Page.loadEventFired', 'params': {'timestamp': 1380679.967344}}
                        await tab.goto('http://httpbin.org/get')
                        async for data in e:
                            print(data)
                            break
        """
        return EventBuffer(events,
                           tab=self,
                           maxsize=maxsize,
                           timeout=timeout,
                           kwargs=kwargs,
                           callback=callback)

    def iter_fetch(self,
                   patterns: List[dict] = None,
                   handleAuthRequests=False,
                   events: List[str] = None,
                   timeout: Union[float, int] = None,
                   maxsize=0,
                   kwargs: Any = None,
                   callback: Callable = None) -> 'FetchBuffer':
        """
Fetch.RequestPattern:

    urlPattern
        string(Wildcards)
    resourceType
        Document, Stylesheet, Image, Media, Font, Script, TextTrack, XHR, Fetch, EventSource, WebSocket, Manifest, SignedExchange, Ping, CSPViolationReport, Preflight, Other
    requestStage
        Stage at which to begin intercepting requests. Default is Request.
        Allowed Values: Request, Response

Demo::

    async with tab.iter_fetch(patterns=[{
            'urlPattern': '*httpbin.org/get?a=*'
    }]) as f:
        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        # test continueRequest
        await f.continueRequest(data)
        assert await tab.wait_includes('origin')

        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        # test modify response
        await f.fulfillRequest(data,
                                200,
                                body=b'hello world.')
        assert await tab.wait_includes('hello world.')
        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        await f.failRequest(data, 'AccessDenied')
        assert (await tab.url).startswith('chrome-error://')

    # use callback
    async def cb(event, tab, buffer):
        await buffer.continueRequest(event)

    async with tab.iter_fetch(
            patterns=[{
                'urlPattern': '*httpbin.org/ip*'
            }],
            callback=cb,
    ) as f:
        await tab.goto('http://httpbin.org/ip', timeout=0)
        async for r in f:
            break

        """
        return FetchBuffer(events=events,
                           tab=self,
                           patterns=patterns,
                           handleAuthRequests=handleAuthRequests,
                           timeout=timeout,
                           maxsize=maxsize,
                           kwargs=kwargs,
                           callback=callback)

    async def pass_auth_proxy(self,
                              user='',
                              password='',
                              test_url='https://api.github.com/',
                              callback: Callable = None,
                              iter_count=2):
        """pass user/password for auth proxy.

        Demo::

            import asyncio

            from ichrome import AsyncChromeDaemon


            async def main():
                async with AsyncChromeDaemon(proxy='http://127.0.0.1:10800',
                                            clear_after_shutdown=True,
                                            headless=1) as cd:
                    async with cd.connect_tab() as tab:
                        await tab.pass_auth_proxy('user', 'pwd')
                        await tab.goto('http://httpbin.org/ip', timeout=2)
                        print(await tab.html)


            asyncio.run(main())
"""
        ok = False
        async with self.iter_fetch(handleAuthRequests=True) as f:
            try:
                task = asyncio.create_task(self.goto(test_url, timeout=1))
                for _ in range(iter_count):
                    if ok:
                        break
                    event: dict = await f
                    if event['method'] == 'Fetch.requestPaused':
                        await f.continueRequest(event)
                    elif event['method'] == 'Fetch.authRequired':
                        if callback:
                            ok = await ensure_awaitable(callback(event))
                        else:
                            await f.continueWithAuth(
                                event,
                                'ProvideCredentials',
                                user,
                                password,
                            )
                            ok = True
            finally:
                await task
                return ok

    async def get_response(
        self,
        request_dict: Union[None, dict, str],
        timeout=NotSet,
        wait_loading: bool = None,
    ) -> Union[dict, None]:
        '''return Network.getResponseBody raw response.
        return demo:

                {'id': 2, 'result': {'body': 'source code', 'base64Encoded': False}}

        some ajax request need to await tab.wait_request_loading(request_dict) for
        loadingFinished (or sleep some secs) and wait_loading=None will auto check response loaded.'''
        request_id = self._ensure_request_id(request_dict)
        result = None
        if request_id is None:
            return result
        timeout = self.ensure_timeout(timeout)
        if wait_loading is None:
            data = await self.send("Network.getResponseBody",
                                   requestId=request_id,
                                   timeout=timeout)
            if self.get_data_value(data, 'error.code') != -32000:
                return data
        if wait_loading is not False:
            # ensure the request loaded
            await self.wait_request_loading(request_id, timeout=timeout)
        return await self.send("Network.getResponseBody",
                               requestId=request_id,
                               timeout=timeout)

    async def get_response_body(self,
                                request_dict: Union[None, dict, str],
                                timeout=NotSet,
                                wait_loading=None) -> Union[dict, None]:
        """get result.body from self.get_response."""
        result = await self.get_response(request_dict,
                                         timeout=timeout,
                                         wait_loading=wait_loading)
        return self.get_data_value(result, value_path='result.body', default='')

    async def get_request_post_data(self,
                                    request_dict: Union[None, dict, str],
                                    timeout=NotSet) -> Union[str, None]:
        """Get the post data of the POST request. No need for wait_request_loading."""
        request_id = self._ensure_request_id(request_dict)
        if request_id is None:
            return None
        result = await self.send("Network.getRequestPostData",
                                 requestId=request_id,
                                 timeout=timeout)
        return self.get_data_value(result, value_path='result.postData')

    async def reload(self,
                     ignoreCache: bool = False,
                     scriptToEvaluateOnLoad: str = None,
                     timeout=NotSet):
        """Reload the page.

        ignoreCache: If true, browser cache is ignored (as if the user pressed Shift+refresh).
        scriptToEvaluateOnLoad: If set, the script will be injected into all frames of the inspected page after reload.

        Argument will be ignored if reloading dataURL origin."""
        if scriptToEvaluateOnLoad is None:
            return await self.send('Page.reload',
                                   ignoreCache=ignoreCache,
                                   timeout=timeout)
        else:
            return await self.send(
                'Page.reload',
                ignoreCache=ignoreCache,
                scriptToEvaluateOnLoad=scriptToEvaluateOnLoad,
                timeout=timeout)

    async def set_headers(self, headers: dict, timeout=NotSet):
        logger.debug(f'[set_headers] {self!r} headers => {headers}')
        data = await self.send('Network.setExtraHTTPHeaders',
                               headers=headers,
                               timeout=timeout)
        return data

    async def set_ua(self,
                     userAgent: str,
                     acceptLanguage: Optional[str] = '',
                     platform: Optional[str] = '',
                     timeout=NotSet):
        "[Network.setUserAgentOverride], reset the User-Agent of this tab"
        logger.debug(f'[set_ua] {self!r} userAgent => {userAgent}')
        data = await self.send('Network.setUserAgentOverride',
                               userAgent=userAgent,
                               acceptLanguage=acceptLanguage,
                               platform=platform,
                               timeout=timeout)
        return data

    async def goto_history(self, entryId: int = 0, timeout=NotSet) -> bool:
        "[Page.navigateToHistoryEntry]"
        result = await self.send('Page.navigateToHistoryEntry',
                                 entryId=entryId,
                                 timeout=timeout)
        return self.check_error('goto_history', result, entryId=entryId)

    async def get_history_entry(self,
                                index: int = None,
                                relative_index: int = None,
                                timeout=NotSet):
        "get history entries of this page"
        result = await self.get_history_list(timeout=timeout)
        if result:
            if index is None:
                index = result['currentIndex'] + relative_index
                return result['entries'][index]
            elif relative_index is None:
                return result['entries'][index]
            else:
                raise ChromeValueError(
                    'index and relative_index should not be both None.')

    async def history_back(self, timeout=NotSet):
        "go to back history"
        return await self.goto_history_relative(relative_index=-1,
                                                timeout=timeout)

    async def history_forward(self, timeout=NotSet):
        "go to forward history"
        return await self.goto_history_relative(relative_index=1,
                                                timeout=timeout)

    async def goto_history_relative(self,
                                    relative_index: int = None,
                                    timeout=NotSet):
        "go to the relative history"
        try:
            entry = await self.get_history_entry(relative_index=relative_index,
                                                 timeout=timeout)
        except IndexError:
            return None
        entry_id = self.get_data_value(entry, 'id')
        if entry_id is not None:
            return await self.goto_history(entryId=entry_id, timeout=timeout)
        return False

    async def get_history_list(self, timeout=NotSet) -> dict:
        """(Page.getNavigationHistory) Get the page history list.
        return example:
            {'currentIndex': 0, 'entries': [{'id': 1, 'url': 'about:blank', 'userTypedURL': 'about:blank', 'title': '', 'transitionType': 'auto_toplevel'}, {'id': 7, 'url': 'http://3.p.cn/', 'userTypedURL': 'http://3.p.cn/', 'title': 'Not Found', 'transitionType': 'typed'}, {'id': 9, 'url': 'http://p.3.cn/', 'userTypedURL': 'http://p.3.cn/', 'title': '', 'transitionType': 'typed'}]}}"""
        result = await self.send('Page.getNavigationHistory', timeout=timeout)
        return self.get_data_value(result, value_path='result', default={})

    async def reset_history(self, timeout=NotSet) -> bool:
        "[Page.resetNavigationHistory], clear up history immediately"
        result = await self.send('Page.resetNavigationHistory', timeout=timeout)
        return self.check_error('reset_history', result)

    async def setBlockedURLs(self, urls: List[str], timeout=NotSet):
        """(Network.setBlockedURLs) Blocks URLs from loading. [EXPERIMENTAL].

Demo::

    await tab.setBlockedURLs(urls=['*.jpg', '*.png'])

WARNING: This method is EXPERIMENTAL, the official suggestion is using Fetch.enable, even Fetch is also EXPERIMENTAL, and wait events to control the requests (continue / abort / modify), especially block urls with resourceType: Document, Stylesheet, Image, Media, Font, Script, TextTrack, XHR, Fetch, EventSource, WebSocket, Manifest, SignedExchange, Ping, CSPViolationReport, Other.
https://chromedevtools.github.io/devtools-protocol/tot/Fetch/#method-enable
        """
        return await self.send('Network.setBlockedURLs',
                               urls=urls,
                               timeout=timeout)

    async def goto(self,
                   url: Optional[str] = None,
                   referrer: Optional[str] = None,
                   timeout=NotSet,
                   timeout_stop_loading: bool = False) -> bool:
        "alias for self.set_url"
        return await self.set_url(url=url,
                                  referrer=referrer,
                                  timeout=timeout,
                                  timeout_stop_loading=timeout_stop_loading)

    async def set_url(self,
                      url: Optional[str] = None,
                      referrer: Optional[str] = None,
                      timeout=NotSet,
                      timeout_stop_loading: bool = False) -> bool:
        """
        Navigate the tab to the URL. If stop loading occurs, return False.
        """
        logger.debug(f'[set_url] {self!r} url => {url}')
        if timeout == 0:
            # no need wait loading
            loaded_task = None
        else:
            # register loading event before seting url
            loaded_task = asyncio.ensure_future(
                self.wait_loading(timeout=timeout,
                                  timeout_stop_loading=timeout_stop_loading))
        if url:
            self._url = url
            if referrer is None:
                data = await self.send("Page.navigate",
                                       url=url,
                                       timeout=timeout)
            else:
                data = await self.send("Page.navigate",
                                       url=url,
                                       referrer=referrer,
                                       timeout=timeout)
        else:
            data = await self.reload(timeout=timeout)
        # loadEventFired return True, else return False
        if loaded_task:
            loaded_ok = await loaded_task
        else:
            loaded_ok = False
        return bool(data and loaded_ok)

    async def js(self,
                 javascript: str,
                 value_path='result.result',
                 kwargs=None,
                 timeout=NotSet):
        """
        Evaluate JavaScript on the page.
        `js_result = await tab.js('document.title', timeout=10)`
        js_result:
            {'id': 18, 'result': {'result': {'type': 'string', 'value': 'Welcome to Python.org'}}}
        return None while timeout.
        kwargs is a dict for Runtime.evaluate's `timeout` is conflict with `timeout` of self.send.
        """
        result = await self.send("Runtime.evaluate",
                                 timeout=timeout,
                                 expression=javascript,
                                 kwargs=kwargs)
        logger.debug(
            f'[js] {self!r} insert js `{javascript}`, received: {result}.')
        return self.get_data_value(result, value_path)

    async def js_code(self,
                      javascript: str,
                      value_path='result.result.value',
                      kwargs=None,
                      timeout=NotSet):
        """javascript will be filled into function template.

Demo::

    javascript = `return document.title`
    will run js like `(()=>{return document.title})()`, and get the return result
"""
        javascript = '''(()=>{%s})()''' % javascript
        return await self.js(javascript,
                             value_path=value_path,
                             kwargs=kwargs,
                             timeout=timeout)

    async def handle_dialog(self,
                            accept=True,
                            promptText=None,
                            timeout=NotSet) -> bool:
        """WARNING: you should enable `Page` domain explicitly before running tab.js('alert()'), because alert() will always halt the event loop."""
        kwargs = {'timeout': timeout, 'accept': accept}
        if promptText is not None:
            kwargs['promptText'] = promptText
        result = await self.send('Page.handleJavaScriptDialog', **kwargs)
        return self.check_error('handle_dialog',
                                result,
                                accept=accept,
                                promptText=promptText)

    async def wait_tag_click(self,
                             cssselector: str,
                             max_wait_time: Optional[float] = None,
                             interval: float = 1,
                             timeout=NotSet):
        "wait the tag appeared and click it"
        tag = await self.wait_tag(cssselector,
                                  max_wait_time=max_wait_time,
                                  interval=interval,
                                  timeout=timeout)
        if tag:
            result = await self.click(cssselector=cssselector, timeout=timeout)
            return result
        else:
            return None

    async def wait_tag(self,
                       cssselector: str,
                       max_wait_time: Optional[float] = None,
                       interval: float = 1,
                       timeout=NotSet) -> Union[None, Tag, TagNotFound]:
        '''Wait until the tag is ready or max_wait_time used up, sometimes it is more useful than wait loading.
        cssselector: css querying the Tag.
        interval: checking interval for while loop.
        max_wait_time: if time used up, return None.
        timeout: timeout seconds for sending a msg.

        If max_wait_time used up: return [].
        elif querySelectorAll runs failed, return None.
        else: return List[Tag]
        WARNING: methods with prefix `wait_` the `timeout` default to None.
        '''
        tag = None
        TIMEOUT_AT = time.time() + self.ensure_timeout(max_wait_time)
        while TIMEOUT_AT > time.time():
            tag = await self.querySelector(cssselector=cssselector,
                                           timeout=timeout)
            if tag:
                break
            await asyncio.sleep(interval)
        return tag or None

    async def wait_tags(self,
                        cssselector: str,
                        max_wait_time: Optional[float] = None,
                        interval: float = 1,
                        timeout=NotSet) -> Union[List[Tag], Tag, TagNotFound]:
        '''Wait until the tags is ready or max_wait_time used up, sometimes it is more useful than wait loading.
        cssselector: css querying the Tags.
        interval: checking interval for while loop.
        max_wait_time: if time used up, return [].
        timeout: timeout seconds for sending a msg.

        If max_wait_time used up: return [].
        elif querySelectorAll runs failed, return None.
        else: return List[Tag]
        WARNING: methods with prefix `wait_` the `timeout` default to None.
        '''
        TIMEOUT_AT = time.time() + self.ensure_timeout(max_wait_time)
        while TIMEOUT_AT > time.time():
            tags = await self.querySelectorAll(cssselector=cssselector,
                                               timeout=timeout)
            if tags:
                return tags
            await asyncio.sleep(interval)
        return []

    async def wait_findall(self,
                           regex: str,
                           cssselector: str = 'html',
                           attribute: str = 'outerHTML',
                           flags: str = 'g',
                           max_wait_time: Optional[float] = None,
                           interval: float = 1,
                           timeout=NotSet) -> list:
        '''while loop until await tab.findall got somethine.'''
        result = []
        TIMEOUT_AT = time.time() + self.ensure_timeout(max_wait_time)
        while TIMEOUT_AT > time.time():
            result = await self.findall(regex=regex,
                                        cssselector=cssselector,
                                        attribute=attribute,
                                        flags=flags,
                                        timeout=timeout)
            if result:
                break
            await asyncio.sleep(interval)
        return result

    async def findone(self,
                      regex: str,
                      cssselector: str = 'html',
                      attribute: str = 'outerHTML',
                      timeout=NotSet):
        "find the string in html(select with given css)"
        result = await self.findall(regex=regex,
                                    cssselector=cssselector,
                                    attribute=attribute,
                                    timeout=timeout)
        if result:
            return result[0]
        return None

    async def findall(self,
                      regex: str,
                      cssselector: str = 'html',
                      attribute: str = 'outerHTML',
                      flags: str = 'g',
                      timeout=NotSet) -> list:
        """Similar to python re.findall.

        Args:
            regex (str): raw regex string to be set in /%s/g.
            cssselector (str, optional): which element.outerHTML to be matched, defaults to 'html'.
            attribute (str, optional): attribute of the selected element, defaults to 'outerHTML'
            flags (str, optional): regex flags, defaults to 'g'.
            timeout (float): defaults to NotSet.

Demo::

    # no group / (?:) / (?<=) / (?!)
    print(await tab.findall('<title>.*?</title>'))
    # ['<title>123456789</title>']

    # only 1 group
    print(await tab.findall('<title>(.*?)</title>'))
    # ['123456789']

    # multi-groups
    print(await tab.findall('<title>(1)(2).*?</title>'))
    # [['1', '2']]
        """
        if re.search(r'(?<!\\)/', regex):
            regex = re.sub(r'(?<!\\)/', r'\/', regex)
        group_count = len(re.findall(r'(?<!\\)\((?!\?)', regex))
        act = 'matchAll' if 'g' in flags else 'match'
        code = '''
var group_count = %s
var result = []
var items = [...document.querySelector(`%s`).%s.%s(/%s/%s)]
items.forEach((item) => {
    if (group_count <= 1) {
        result.push(item[group_count])
    } else {
        var tmp = []
        for (let i = 1; i < group_count + 1; i++) {
            tmp.push(item[i])
        }
        result.push(tmp)
    }
})
JSON.stringify(result)
''' % (group_count, cssselector, attribute, act, regex, flags)
        result = await self.js(code,
                               value_path='result.result.value',
                               timeout=timeout)
        if result and result.startswith('['):
            return json.loads(result)
        else:
            return []

    async def contains(self,
                       text,
                       cssselector: str = 'html',
                       attribute: str = 'outerHTML',
                       timeout=NotSet) -> bool:
        """alias for Tab.includes"""
        return await self.includes(text=text,
                                   cssselector=cssselector,
                                   attribute=attribute,
                                   timeout=timeout)

    async def includes(self,
                       text,
                       cssselector: str = 'html',
                       attribute: str = 'outerHTML',
                       timeout=NotSet) -> bool:
        """String.prototype.includes.

        Args:
            text (str): substring
            cssselector (str, optional): css selector for outerHTML, defaults to 'html'
            attribute (str, optional): attribute of the selected element, defaults to 'outerHTML'. Sometimes for case-insensitive usage by setting `attribute='textContent.toLowerCase()'`
        Returns:
            whether the outerHTML contains substring.
        """
        js = f'document.querySelector(`{cssselector}`).{attribute}.includes(`{text}`)'
        return await self.get_value(js, jsonify=True, timeout=timeout)

    async def wait_includes(self,
                            text: str,
                            cssselector: str = 'html',
                            attribute: str = 'outerHTML',
                            max_wait_time: Optional[float] = None,
                            interval: float = 1,
                            timeout=NotSet) -> bool:
        '''while loop until element contains the substring.'''
        exist = False
        TIMEOUT_AT = time.time() + self.ensure_timeout(max_wait_time)
        while TIMEOUT_AT > time.time():
            exist = await self.includes(text=text,
                                        cssselector=cssselector,
                                        attribute=attribute,
                                        timeout=timeout)
            if exist:
                return exist
            await asyncio.sleep(interval)
        return exist

    async def querySelector(self,
                            cssselector: str,
                            action: Union[None, str] = None,
                            timeout=NotSet) -> Union[Tag, TagNotFound]:
        "deprecated. query a tag with css"
        return await self.querySelectorAll(cssselector=cssselector,
                                           index=0,
                                           action=action,
                                           timeout=timeout)

    async def querySelectorAll(
            self,
            cssselector: str,
            index: Union[None, int, str] = None,
            action: Union[None, str] = None,
            timeout=NotSet) -> Union[List[Tag], Tag, TagNotFound]:
        """deprecated. CDP DOM domain is quite heavy both computationally and memory wise, use js instead. return List[Tag], Tag, TagNotFound.
        Tag hasattr: tagName, innerHTML, outerHTML, textContent, attributes, result

        If index is not None, will return the tag_list[index], else return the whole tag list.

        Demo:

            # 1. get attribute of the selected tag

            tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0, action="getAttribute('href')")).result
            tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0)).get('href')
            tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0)).to_dict()

            # 2. remove href attr of all the selected tags
            tags = await tab.querySelectorAll("#sc_hdu>li>a", action="removeAttribute('href')")

            for tag in tab.querySelectorAll("#sc_hdu>li"):
                print(tag.attributes)

        """
        if "'" in cssselector:
            cssselector = cssselector.replace("'", "\\'")
        if index is None:
            index = "null"
        else:
            index = int(index)
        if action:
            # do the action and set Tag.result as el.action result
            _action = f"item.result=el.{action} || '';item.result=item.result.toString()"
            action = 'try {%s} catch (error) {}' % _action
        else:
            action = ""
        javascript = """
var index_filter = %s
var css = `%s`
if (index_filter == 0) {
    var element = document.querySelector(css)
    if (element) {
        var elements = [element]
    } else {
        var elements = []
    }
} else {
    var elements = document.querySelectorAll(css)
}
var result = []
for (let index = 0; index < elements.length; index++) {
    const el = elements[index];
    if (index_filter!=null && index_filter!=index) {
        continue
    }

    var item = {
        tagName: el.tagName,
        innerHTML: el.innerHTML,
        outerHTML: el.outerHTML,
        textContent: el.textContent,
        result: null,
        attributes: {}
    }
    for (const attr of el.attributes) {
        item.attributes[attr.name] = attr.value
    }
    %s
    result.push(item)
}
JSON.stringify(result)""" % (
            index,
            cssselector,
            action,
        )
        response = None
        try:
            response_items_str = (await
                                  self.js(javascript,
                                          timeout=timeout,
                                          value_path='result.result.value'))
            try:
                items = json.loads(
                    response_items_str) if response_items_str else []
            except (json.JSONDecodeError, ValueError):
                items = []
            result = [Tag(**kws) for kws in items]
            if isinstance(index, int):
                if result:
                    return result[0]
                else:
                    return TagNotFound()
            else:
                return result
        except Exception as error:
            logger.error(
                f"querySelectorAll error: {error!r}, response: {response}")
            raise error

    async def insertAdjacentHTML(self,
                                 html: str,
                                 cssselector: str = 'body',
                                 position: str = 'beforeend',
                                 timeout=NotSet):
        """Insert HTML source code into document. Often used for injecting CSS element.

        Args:
            html (str): HTML source code
            cssselector (str, optional): cssselector to find the target node, defaults to 'body'
            position (str, optional): ['beforebegin', 'afterbegin', 'beforeend', 'afterend'],  defaults to 'beforeend'
            timeout ([type], optional): defaults to NotSet
        """
        template = f'''document.querySelector(`{cssselector}`).insertAdjacentHTML('{position}', `{html}`)'''
        return await self.js(template, timeout=timeout)

    async def inject_html(self,
                          html: str,
                          cssselector: str = 'body',
                          position: str = 'beforeend',
                          timeout=NotSet):
        """An alias name for tab.insertAdjacentHTML."""
        return await self.insertAdjacentHTML(html=html,
                                             cssselector=cssselector,
                                             position=position,
                                             timeout=timeout)

    async def inject_js_url(self,
                            url,
                            timeout=None,
                            retry=0,
                            verify=False,
                            **requests_kwargs) -> Union[dict, None]:
        "inject and run the given JS URL"
        if not requests_kwargs.get('headers'):
            requests_kwargs['headers'] = {'User-Agent': UA.Chrome}
        r = await self.req.get(url,
                               timeout=timeout,
                               retry=retry,
                               ssl=verify,
                               **requests_kwargs)
        if r:
            javascript = r.text
            return await self.js(javascript, timeout=timeout)
        else:
            logger.error(f"inject_js_url failed for request: {r.text}")
            return None

    async def click(self,
                    cssselector: str,
                    index: int = 0,
                    action: str = "click()",
                    timeout=NotSet) -> Union[List[Tag], Tag, None]:
        """Click some tag with javascript
        await tab.click("#sc_hdu>li>a") # click first node's link.
        await tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
        """
        return await self.querySelectorAll(cssselector,
                                           index=index,
                                           action=action,
                                           timeout=timeout)

    async def get_element_clip(self,
                               cssselector: str,
                               scale=1,
                               timeout=NotSet,
                               captureBeyondViewport=False):
        """Element.getBoundingClientRect. If captureBeyondViewport is True, use scrollWidth & scrollHeight instead.
        {"x":241,"y":85.59375,"width":165,"height":36,"top":85.59375,"right":406,"bottom":121.59375,"left":241}
        """
        if captureBeyondViewport:
            js_str = 'node=document.querySelector(`%s`);rect = node.getBoundingClientRect();rect.width=node.scrollWidth;rect.height=node.scrollHeight;JSON.stringify(rect)' % cssselector
        else:
            js_str = 'node=document.querySelector(`%s`);rect = node.getBoundingClientRect();JSON.stringify(rect)' % cssselector
        rect = await self.js(js_str,
                             timeout=timeout,
                             value_path='result.result.value')
        if rect:
            try:
                rect = json.loads(rect)
                rect['scale'] = scale
                return rect
            except (TypeError, KeyError, json.JSONDecodeError):
                pass

    async def snapshot_mhtml(self,
                             save_path=None,
                             encoding='utf-8',
                             timeout=NotSet,
                             **kwargs):
        """[Page.captureSnapshot], as the mhtml page"""
        result = await self.send('Page.captureSnapshot',
                                 timeout=timeout,
                                 callback_function=lambda r: self.
                                 get_data_value(r, 'result.data', default=''),
                                 **kwargs)
        if result and save_path:

            def save_file():
                with open(save_path, 'w', encoding=encoding) as f:
                    f.write(result)

            await async_run(save_file)
        return result

    async def screenshot_element(self,
                                 cssselector: str = None,
                                 scale=1,
                                 format: str = 'png',
                                 quality: int = 100,
                                 fromSurface: bool = True,
                                 save_path=None,
                                 timeout=NotSet,
                                 captureBeyondViewport=False,
                                 **kwargs):
        "screenshot the tag selected with given css as a picture"
        if cssselector:
            clip = await self.get_element_clip(
                cssselector,
                scale=scale,
                captureBeyondViewport=captureBeyondViewport)
        else:
            clip = None
        return await self.screenshot(
            format=format,
            quality=quality,
            clip=clip,
            fromSurface=fromSurface,
            save_path=save_path,
            timeout=timeout,
            captureBeyondViewport=captureBeyondViewport,
            **kwargs)

    async def screenshot(self,
                         format: str = 'png',
                         quality: int = 100,
                         clip: dict = None,
                         fromSurface: bool = True,
                         save_path=None,
                         timeout=NotSet,
                         captureBeyondViewport=False,
                         **kwargs):
        """Page.captureScreenshot. clip's keys: x, y, width, height, scale

        format(str, optional): Image compression format (defaults to png)., defaults to 'png'
        quality(int, optional): Compression quality from range [0..100], defaults to None. (jpeg only).
        clip(dict, optional): Capture the screenshot of a given region only. defaults to None, means whole page.
        fromSurface(bool, optional): Capture the screenshot from the surface, rather than the view. Defaults to true.
"""

        def save_file(save_path, file_bytes):
            with open(save_path, 'wb') as f:
                f.write(file_bytes)

        kwargs.update(format=format, quality=quality, fromSurface=fromSurface)
        if clip:
            kwargs['clip'] = clip
        result = await self.send('Page.captureScreenshot',
                                 timeout=timeout,
                                 captureBeyondViewport=captureBeyondViewport,
                                 **kwargs)
        base64_img = self.get_data_value(result, value_path='result.data')
        if save_path and base64_img:
            file_bytes = b64decode(base64_img)
            await async_run(save_file, save_path, file_bytes)
        return base64_img

    async def add_js_onload(self, source: str, **kwargs) -> str:
        '''[Page.addScriptToEvaluateOnNewDocument], return the identifier [str].'''
        data = await self.send('Page.addScriptToEvaluateOnNewDocument',
                               source=source,
                               **kwargs)
        return self.get_data_value(data, value_path='result.identifier') or ''

    async def remove_js_onload(self, identifier: str, timeout=NotSet) -> bool:
        '''[Page.removeScriptToEvaluateOnNewDocument], return whether the identifier exist.'''
        result = await self.send('Page.removeScriptToEvaluateOnNewDocument',
                                 identifier=identifier,
                                 timeout=timeout)
        return self.check_error('remove_js_onload',
                                result,
                                identifier=identifier)

    async def get_screen_size(self, timeout=NotSet):
        "get [window.screen.width, window.screen.height] with javascript"
        return await self.get_value(
            '[window.screen.width, window.screen.height]', timeout=timeout)

    async def get_page_size(self, timeout=NotSet):
        "get page size with javascript"
        return await self.get_value(
            "[window.innerWidth||document.documentElement.clientWidth||document.querySelector('body').clientWidth,window.innerHeight||document.documentElement.clientHeight||document.querySelector('body').clientHeight]",
            timeout=timeout)

    async def keyboard_send(self,
                            *,
                            type='char',
                            timeout=NotSet,
                            string=None,
                            **kwargs):
        '''[Input.dispatchKeyEvent]

        type: keyDown, keyUp, rawKeyDown, char.
        string: will be split into chars.

        kwargs:
            text, unmodifiedText, keyIdentifier, code, key...

        https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchKeyEvent

        Keyboard Events:
            code:
                https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/code
            key:
                https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key
            keyIdentifier(Deprecated):
                https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/keyIdentifier
        '''
        if string:
            result = None
            for char in string:
                result = await self.keyboard_send(text=char, timeout=timeout)
            return result
        else:
            return await self.send('Input.dispatchKeyEvent',
                                   type=type,
                                   timeout=timeout,
                                   **kwargs)

    async def mouse_click_element_rect(self,
                                       cssselector: str,
                                       button='left',
                                       count=1,
                                       scale=1,
                                       multiplier=(0.5, 0.5),
                                       timeout=NotSet):
        "dispatchMouseEvent on selected element center"
        rect = await self.get_element_clip(cssselector,
                                           scale=scale,
                                           timeout=timeout)
        if rect:
            x = rect['x'] + multiplier[0] * rect['width']
            y = rect['y'] + multiplier[1] * rect['height']
            await self.mouse_press(x=x,
                                   y=y,
                                   button=button,
                                   count=count,
                                   timeout=timeout)
            return await self.mouse_release(x=x,
                                            y=y,
                                            button=button,
                                            count=1,
                                            timeout=timeout)

    async def mouse_click(self, x, y, button='left', count=1, timeout=NotSet):
        "click a position"
        await self.mouse_press(x=x,
                               y=y,
                               button=button,
                               count=count,
                               timeout=timeout)
        return await self.mouse_release(x=x,
                                        y=y,
                                        button=button,
                                        count=1,
                                        timeout=timeout)

    async def mouse_press(self, x, y, button='left', count=0, timeout=NotSet):
        "Input.dispatchMouseEvent + mousePressed"
        return await self.send('Input.dispatchMouseEvent',
                               type="mousePressed",
                               x=x,
                               y=y,
                               button=button,
                               clickCount=count,
                               timeout=timeout)

    async def mouse_release(self, x, y, button='left', count=0, timeout=NotSet):
        "Input.dispatchMouseEvent + mouseReleased"
        return await self.send('Input.dispatchMouseEvent',
                               type="mouseReleased",
                               x=x,
                               y=y,
                               button=button,
                               clickCount=count,
                               timeout=timeout)

    @staticmethod
    def get_smooth_steps(target_x, target_y, start_x, start_y, steps_count=30):
        "smooth move steps"

        def getPointOnLine(x1, y1, x2, y2, n):
            """Returns the (x, y) tuple of the point that has progressed a proportion
            n along the line defined by the two x, y coordinates.

            Copied from pyautogui & pytweening module.
            """
            x = ((x2 - x1) * n) + x1
            y = ((y2 - y1) * n) + y1
            return (x, y)

        steps = [
            getPointOnLine(start_x, start_y, target_x, target_y,
                           n / steps_count) for n in range(steps_count)
        ]
        # steps = [(int(a), int(b)) for a, b in steps]
        steps.append((target_x, target_y))
        return steps

    async def mouse_move(self,
                         target_x,
                         target_y,
                         start_x=None,
                         start_y=None,
                         duration=0,
                         timeout=NotSet):
        "move mouse smoothly only if duration > 0."
        if start_x is None:
            start_x = 0.8 * target_x
        if start_y is None:
            start_y = 0.8 * target_y
        if duration:
            size = await self.get_page_size()
            if size:
                steps_count = int(max(size))
            else:
                steps_count = int(
                    max([abs(target_x - start_x),
                         abs(target_y - start_y)]))
            steps_count = steps_count or 30
            interval = duration / steps_count
            if interval < self._min_move_interval:
                steps_count = int(duration / self._min_move_interval)
                interval = duration / steps_count
            steps = self.get_smooth_steps(target_x,
                                          target_y,
                                          start_x,
                                          start_y,
                                          steps_count=steps_count)
        else:
            interval = 0
            steps = [(target_x, target_y)]
        for x, y in steps:
            await asyncio.sleep(interval)
            await self.send('Input.dispatchMouseEvent',
                            type="mouseMoved",
                            x=int(round(x)),
                            y=int(round(y)),
                            timeout=timeout)
        return (target_x, target_y)

    async def mouse_move_rel(self,
                             offset_x,
                             offset_y,
                             start_x,
                             start_y,
                             duration=0,
                             timeout=NotSet):
        '''Move mouse with offset.

        Example::

                await tab.mouse_move_rel(x + 15, 3, start_x, start_y, duration=0.3)
'''
        target_x = start_x + offset_x
        target_y = start_y + offset_y
        await self.mouse_move(start_x=start_x,
                              start_y=start_y,
                              target_x=target_x,
                              target_y=target_y,
                              duration=duration,
                              timeout=timeout)
        return (target_x, target_y)

    def mouse_move_rel_chain(self, start_x, start_y, timeout=NotSet):
        """Move with offset continuously.

        Example::

            walker = await tab.mouse_move_rel_chain(start_x, start_y).move(-20, -5, 0.2).move(5, 1, 0.2)
            walker = await walker.move(-10, 0, 0.2).move(10, 0, 0.5)
"""
        return OffsetMoveWalker(start_x, start_y, tab=self, timeout=timeout)

    async def mouse_drag(self,
                         start_x,
                         start_y,
                         target_x,
                         target_y,
                         button='left',
                         duration=0,
                         timeout=NotSet):
        await self.mouse_press(start_x, start_y, button=button, timeout=timeout)
        await self.mouse_move(target_x,
                              target_y,
                              duration=duration,
                              timeout=timeout)
        await self.mouse_release(target_x,
                                 target_y,
                                 button=button,
                                 timeout=timeout)
        return (target_x, target_y)

    async def mouse_drag_rel(self,
                             start_x,
                             start_y,
                             offset_x,
                             offset_y,
                             button='left',
                             duration=0,
                             timeout=NotSet):
        "drag mouse relatively"
        return await self.mouse_drag(start_x,
                                     start_y,
                                     start_x + offset_x,
                                     start_y + offset_y,
                                     button=button,
                                     duration=duration,
                                     timeout=timeout)

    def mouse_drag_rel_chain(self,
                             start_x,
                             start_y,
                             button='left',
                             timeout=NotSet):
        '''Drag with offset continuously.

Demo::

        await tab.set_url('https://draw.yunser.com/')
        walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
            0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
        await walker.move(50 * 1.414, 50 * 1.414, 0.2)
        '''
        return OffsetDragWalker(start_x,
                                start_y,
                                tab=self,
                                button=button,
                                timeout=timeout)

    async def gc(self):
        "[HeapProfiler.collectGarbage]"
        return await self.send('HeapProfiler.collectGarbage')

    async def alert(self, text, timeout=NotSet):
        """run alert(`{text}`) in console, the `text` should be escaped before passing.
        Block until user click [OK] or timeout.
        Returned as:
            "undefined": [OK] clicked.
            None: timeout.
        """
        result = await self.js('alert(`%s`)' % text, timeout=timeout)
        return self.get_data_value(result, 'type', None)

    async def confirm(self, text, timeout=NotSet):
        """run confirm(`{text}`) in console, the `text` should be escaped before passing.
        Block until user click [OK] or click [Cancel] or timeout.
        Returned as:
            True: [OK] clicked.
            False: [Cancel] clicked.
            None: timeout.
        """
        result = await self.js('confirm(`%s`)' % text, timeout=timeout)
        return self.get_data_value(result, 'value')

    async def prompt(self, text, value=None, timeout=NotSet):
        """run prompt(`{text}`, `value`) in console, the `text` and `value` should be escaped before passing.
        Block until user click [OK] or click [Cancel] or timeout.
        Returned as:
            new value: [OK] clicked.
            None: [Cancel] clicked.
            value: timeout.
        """
        _value = str(value or '')
        result = await self.js('prompt(`%s`, `%s`)' % (text, _value),
                               timeout=timeout)
        return self.get_data_value(result, 'value', value)

    @classmethod
    async def repl(cls, f_globals=None, f_locals=None):
        """Give a simple way to debug your code with ichrome."""
        import traceback
        try:
            import readline as _
        except ImportError:
            pass
        import ast
        import types
        import warnings
        from code import CommandCompiler
        f_globals = f_globals or sys._getframe(1).f_globals
        f_locals = f_locals or sys._getframe(1).f_locals
        for key in {
                '__name__', '__package__', '__loader__', '__spec__',
                '__builtins__', '__file__'
        }:
            f_locals[key] = f_globals[key]
        doc = r'''
Here is ichrome repl demo version, the features is not as good as python pbd, but this is very easy to use.

Shortcuts:
    -h: show more help.
    -q: quit the repl mode.
    CTRL-C: clear current line.

Demo source code:

```python
from ichrome import AsyncChromeDaemon, repl
import asyncio


async def main():
    async with AsyncChromeDaemon() as cd:
        async with cd.connect_tab() as tab:
            await tab.repl()


if __name__ == "__main__":
    asyncio.run(main())
```
So debug your code with ichrome is only `await tab.repl()`.

For example:

>>> await tab.goto('https://github.com/ClericPy')
True
>>> title = await tab.title
>>> title
'ClericPy (ClericPy) · GitHub'
>>> await tab.click('.pinned-item-list-item-content [href="/ClericPy/ichrome"]')
Tag(a)
>>> await tab.wait_loading(2)
True
>>> await tab.wait_loading(2)
False
>>> await tab.js('document.body.innerHTML="Updated"')
{'type': 'string', 'value': 'Updated'}
>>> await tab.history_back()
True
>>> await tab.set_html('hello world')
{'id': 21, 'result': {}}
>>> await tab.set_ua('no UA')
{'id': 22, 'result': {}}
>>> await tab.goto('http://httpbin.org/user-agent')
True
>>> await tab.html
'<html><head></head><body><pre style="word-wrap: break-word; white-space: pre-wrap;">{\n  "user-agent": "no UA"\n}\n</pre></body></html>'
'''

        _compile = CommandCompiler()
        _compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        warnings.filterwarnings('ignore',
                                message=r'^coroutine .* was never awaited$',
                                category=RuntimeWarning)

        async def run_code():
            buffer = []
            more = None
            while more != 0:
                if more == 1:
                    line = input('... ')
                else:
                    line = input('>>> ')
                if not buffer:
                    if line == '-q':
                        raise SystemExit()
                    elif line == '-h':
                        print(doc)
                        break
                buffer.append(line)
                try:
                    code = _compile('\n'.join(buffer), '<console>', 'single')
                    if code is None:
                        more = 1
                        continue
                    else:
                        func = types.FunctionType(code, f_locals)
                        maybe_coro = func()
                        if inspect.isawaitable(maybe_coro):
                            await maybe_coro
                            return
                        else:
                            return code
                except (OverflowError, SyntaxError, ValueError):
                    traceback.print_exc()
                    raise

        while 1:
            try:
                await run_code()
            except KeyboardInterrupt:
                print()
                continue
            except (EOFError, SystemExit):
                break
            except Exception:
                traceback.print_exc()
        print()

    async def set_file_input(self,
                             filepaths: List[Union[str, Path]],
                             cssselector: str = 'input[type="file"]',
                             root_id: str = None,
                             timeout=NotSet):
        """set file type input nodes with given filepaths.
        1. path of filepaths will be reset as absolute posix path.
        2. all the nodes which matched given cssselector will be set together for using DOM.querySelectorAll.
        3. nodes in iframe tags need a new root_id but not default gotten from DOM.getDocument.
        """
        if isinstance(filepaths, str):
            logger.debug(
                'filepaths is type of str will be reset to [filepaths]')
            filepaths = [filepaths]
        assert isinstance(filepaths, list)
        data = await self.send('DOM.getDocument', timeout=timeout)
        if not root_id:
            root_id = self.get_data_value(data, 'result.root.nodeId')
        if not root_id:
            logger.debug(
                f'set_file_input failed for receive data without root nodeId: {data}'
            )
            return
        data = await self.send('DOM.querySelectorAll',
                               nodeId=root_id,
                               selector=cssselector,
                               timeout=timeout)
        nodeIds = self.get_data_value(data, 'result.nodeIds')
        if not nodeIds:
            logger.debug(
                f'set_file_input failed for receive data without target nodeId: {data}'
            )
            return
        filepaths = [
            Path(filepath).absolute().as_posix() for filepath in filepaths
        ]
        results = []
        for nodeId in nodeIds:
            data = await self.send('DOM.setFileInputFiles',
                                   files=filepaths,
                                   nodeId=nodeId)
            results.append(data)
        return results

    def set_flatten(self):
        "use the flatten mode connection"
        # /devtools/browser/
        if '/devtools/browser/' in self.webSocketDebuggerUrl:
            raise ChromeRuntimeError('browser can not be set flatten mode')
        if self.status == 'connected':
            return
        else:
            self.flatten = True
            self._listener = self.browser._listener
            self._buffers = self.browser._buffers
            self.ws = self.browser.ws

    def __hash__(self):
        return self.tab_id

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __str__(self):
        return f"<Tab({self.status}-{self.chrome!r}): {self.tab_id}>"

    def __repr__(self):
        return f"<Tab({self.status}): {self.tab_id}>"

    def ensure_timeout(self, timeout):
        "replace the timeout variable to real value"
        if timeout is NotSet:
            return self.timeout
        elif timeout is None:
            return self._MAX_WAIT_TIMEOUT or INF
        else:
            return timeout

    @property
    def default_recv_callback(self):
        return self._default_recv_callback

    @default_recv_callback.setter
    def default_recv_callback(self, value):
        "set the default_recv_callback or default_recv_callback list"
        if not value:
            self._default_recv_callback = []
        elif isinstance(value, list):
            self._default_recv_callback = value
        elif callable(value):
            self._default_recv_callback = [value]
        else:
            raise ChromeValueError(
                'default_recv_callback should be list or callable, and you can use tab.default_recv_callback.append(cb) to add new callback'
            )
        self.ensure_callback_type(self.default_recv_callback)

    @default_recv_callback.deleter
    def default_recv_callback(self):
        self._default_recv_callback = []

    @staticmethod
    def ensure_callback_type(_default_recv_callback):
        """
        Ensure callback function has correct args
        """
        must_args = ('tab', 'data_dict')
        for func in _default_recv_callback:
            if not callable(func):
                raise ChromeTypeError(
                    f'callback function ({getattr(func, "__name__", func)}) should be callable'
                )
            if not inspect.isbuiltin(func) and len(
                    func.__code__.co_varnames) != 2:
                raise ChromeTypeError(
                    f'callback function ({getattr(func, "__name__", func)}) should handle two args for {must_args}'
                )

    def __call__(self) -> _WSConnection:
        '''`async with tab() as tab:` or just `async with tab():` and reuse `tab` variable.'''
        return self.connect()

    @property
    def msg_id(self) -> int:
        if self.flatten:
            return self.browser.msg_id
        else:
            self._message_id += 1
            return self._message_id

    @property
    def status(self) -> str:
        if self.flatten:
            connected = bool(self._session_id)
        else:
            connected = bool(self.ws and not self.ws.closed)
        return {True: 'connected', False: 'disconnected'}[connected]

    def connect(self) -> _WSConnection:
        '''`async with tab.connect() as tab:`'''
        self._enabled_domains.clear()
        return self.ws_connection

    @property
    def browser(self) -> 'AsyncTab':
        return self.chrome.browser

    async def _recv_daemon(self):
        """Daemon Coroutine for listening the ws.recv.

        event examples:
        {"id":1,"result":{}}
        {"id":3,"result":{"result":{"type":"string","value":"http://p.3.cn/"}}}
        {"id":2,"result":{"frameId":"7F34509F1831E6F29351784861615D1C","loaderId":"F4BD3CBE619185B514F0F42B0CBCCFA1"}}
        {"method":"Page.frameStartedLoading","params":{"frameId":"7F34509F1831E6F29351784861615D1C"}}
        {"method":"Page.frameNavigated","params":{"frame":{"id":"7F34509F1831E6F29351784861615D1C","loaderId":"F4BD3CBE619185B514F0F42B0CBCCFA1","url":"http://p.3.cn/","securityOrigin":"http://p.3.cn","mimeType":"application/json"}}}
        {"method":"Page.loadEventFired","params":{"timestamp":120277.621681}}
        {"method":"Page.frameStoppedLoading","params":{"frameId":"7F34509F1831E6F29351784861615D1C"}}
        {"method":"Page.domContentEventFired","params":{"timestamp":120277.623606}}
        """
        async for msg in self.ws:
            if self._log_all_recv:
                logger.debug(f'[recv] {self!r} {msg}')
            if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                # Message size xxxx exceeds limit 4194304: reset the max_msg_size(default=20*1024*1024) in Tab.ws_kwargs
                err_msg = f'Receive the {msg.type!r} message which break the recv daemon: "{msg.data}".'
                logger.error(err_msg)
                if self.ws_connection.connected:
                    raise ChromeRuntimeError(err_msg)
                else:
                    break
            if msg.type != WSMsgType.TEXT:
                # ignore
                continue
            data_str = msg.data
            if not data_str:
                continue
            try:
                data_dict = json.loads(data_str)
                # ignore non-dict type msg.data
                if not isinstance(data_dict, dict):
                    continue
            except (TypeError, json.decoder.JSONDecodeError):
                logger.debug(
                    f'[json] data_str can not be json.loads: {data_str}')
                continue
            if 'sessionId' in data_dict:
                _tab = self._sessions.get(data_dict['sessionId'])
                if _tab:
                    default_recv_callback = _tab.default_recv_callback
                else:
                    default_recv_callback = []
            else:
                default_recv_callback = self.default_recv_callback
            for callback in default_recv_callback:
                asyncio.ensure_future(
                    ensure_awaitable(callback(self, data_dict)))
            buffer: asyncio.Queue = self._buffers.get(data_dict.get('method'))
            if buffer:
                asyncio.ensure_future(buffer.put(data_dict))
            f = self._listener.pop_future(data_dict)
            if f and f._state == _PENDING:
                f.set_result(data_dict)
        logger.debug(f'[break] {self!r} _recv_daemon loop break.')
        if self._recv_daemon_break_callback:
            return await _ensure_awaitable_callback_result(
                self._recv_daemon_break_callback, self)

    async def _recv(self, event_dict, timeout,
                    callback_function) -> Union[dict, None]:
        error = None
        try:
            result = None
            await self.auto_enable(event_dict, timeout=timeout)
            f = self._listener.register(event_dict)
            result = await asyncio.wait_for(f, timeout=timeout)
            self._listener.unregister(event_dict)
        except asyncio.TimeoutError:
            logger.debug(f'[timeout] {event_dict} [recv] timeout({timeout}).')
            self._listener.unregister(event_dict)
        except Exception as e:
            logger.debug(f'[error] {event_dict} [recv] {e!r}.')
            error = e
        finally:
            if error:
                raise error
            else:
                return await _ensure_awaitable_callback_result(
                    callback_function, result)

    @property
    def now(self) -> int:
        return int(time.time())

    async def auto_enable(self, event_or_method, timeout=NotSet):
        "auto enable the domain"
        if isinstance(event_or_method, dict):
            method = event_or_method.get('method')
        else:
            method = event_or_method
        if isinstance(method, str):
            domain = method.split('.', 1)[0]
            await self.enable(domain, timeout=timeout)

    @property
    def current_url(self) -> Awaitable[str]:
        return self.get_current_url()

    @staticmethod
    def _ensure_request_id(request_id: Union[None, dict, str]):
        if request_id is None:
            return None
        if isinstance(request_id, str):
            return request_id
        elif isinstance(request_id, dict):
            return AsyncTab.get_data_value(request_id, 'params.requestId')
        else:
            raise ChromeTypeError(
                f"request type should be None or dict or str, but `{type(request_id)}` was given."
            )

    async def get_value(self, name: str, timeout=NotSet, jsonify: bool = False):
        """name or expression. jsonify will transport the data by JSON, such as the array."""
        return await self.get_variable(name, timeout=timeout, jsonify=jsonify)

    async def get_variable(self,
                           name: str,
                           timeout=NotSet,
                           jsonify: bool = False):
        """variable or expression. jsonify will transport the data by JSON, such as the array."""
        # using JSON to keep value type
        if jsonify:
            result = await self.js(f'JSON.stringify({name})',
                                   timeout=timeout,
                                   value_path='result.result.value')
            try:
                if result:
                    return json.loads(result)
            except (TypeError, json.decoder.JSONDecodeError):
                pass
            return result
        else:
            return await self.js(name,
                                 timeout=timeout,
                                 value_path='result.result.value')

    async def browser_version(self, timeout=NotSet):
        "[Browser.getVersion]"
        return await self.send('Browser.getVersion', timeout=timeout)


class OffsetMoveWalker:
    __slots__ = ('path', 'start_x', 'start_y', 'tab', 'timeout')

    def __init__(self, start_x, start_y, tab: AsyncTab, timeout=NotSet):
        self.tab = tab
        self.timeout = timeout
        self.start_x = start_x
        self.start_y = start_y
        self.path: List[tuple] = []

    def move(self, offset_x, offset_y, duration=0):
        self.path.append((offset_x, offset_y, duration))
        return self

    async def start(self):
        while self.path:
            x, y, duration = self.path.pop(0)
            await self.tab.mouse_move_rel(x,
                                          y,
                                          self.start_x,
                                          self.start_y,
                                          duration=duration,
                                          timeout=self.timeout)
            self.start_x += x
            self.start_y += y
        return self

    def __await__(self):
        return self.start().__await__()


class OffsetDragWalker(OffsetMoveWalker):
    __slots__ = ('path', 'start_x', 'start_y', 'tab', 'timeout', 'button')

    def __init__(self,
                 start_x,
                 start_y,
                 tab: AsyncTab,
                 button='left',
                 timeout=None):
        super().__init__(start_x, start_y, tab=tab, timeout=timeout)
        self.button = button

    async def start(self):
        await self.tab.mouse_press(self.start_x,
                                   self.start_y,
                                   button=self.button,
                                   timeout=self.timeout)
        while self.path:
            x, y, duration = self.path.pop(0)
            await self.tab.mouse_move_rel(x,
                                          y,
                                          self.start_x,
                                          self.start_y,
                                          duration=duration,
                                          timeout=self.timeout)
            self.start_x += x
            self.start_y += y
        await self.tab.mouse_release(self.start_x,
                                     self.start_y,
                                     button=self.button,
                                     timeout=self.timeout)
        return self


class Listener:
    _SINGLETON_EVENT_KEY = True

    def __init__(self):
        self._registered_futures = WeakValueDictionary()

    @staticmethod
    def _normalize_dict(dict_obj):
        """input a dict_obj, return the hashable item list."""
        if not dict_obj:
            return None
        result = []
        for item in dict_obj.items():
            key = item[0]
            try:
                value = json.dumps(item[1], sort_keys=1)
            except TypeError:
                value = str(item[1])
            result.append((key, value))
        return tuple(result)

    def _arg_to_key(self, event_dict):
        if not isinstance(event_dict, dict):
            logger.error(
                "Listener event_dict should be dict type, such as {'id': 1} or {'method': 'Page.loadEventFired'}"
            )
        if "id" in event_dict:
            # id is unique
            key = f'id={event_dict["id"]}'
        elif "method" in event_dict:
            # method may be duplicate
            key = f'method={event_dict["method"]}'
        else:
            key = f'json={self._normalize_dict(event_dict)}'
        return f'{key}@{event_dict.get("sessionId")}'

    def register(self, event_dict: dict):
        '''Listener will register a event_dict, such as {'id': 1} or {'method': 'Page.loadEventFired'}, maybe the dict doesn't has key [method].'''
        key = self._arg_to_key(event_dict)
        if key in self._registered_futures:
            msg = f'Event key duplicated: {key}'
            logger.warning(msg)
            if self._SINGLETON_EVENT_KEY:
                raise ChromeValueError(msg)
        f: Future = Future()
        self._registered_futures[key] = f
        return f

    def find_future(self, event_dict, default=None):
        key = self._arg_to_key(event_dict)
        return self._registered_futures.get(key, default)

    def pop_future(self, event_dict, default=None):
        key = self._arg_to_key(event_dict)
        return self._registered_futures.pop(key, default)

    def unregister(self, event_dict: dict):
        f = self.pop_future(event_dict)
        if f:
            del f
            return True
        else:
            return False


class AsyncChrome(GetValueMixin):
    _DEFAULT_CONNECT_TIMEOUT = 3
    _DEFAULT_RETRY = 1

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 9222,
                 timeout: int = None,
                 retry: int = None):
        self.host = host
        # port can be null for chrome address without port.
        self.port = port
        self.timeout = timeout or self._DEFAULT_CONNECT_TIMEOUT
        self.retry = self._DEFAULT_RETRY if retry is None else retry
        self.status = 'init'
        self._req = None
        self._browser: AsyncTab = None

    @property
    def browser(self) -> AsyncTab:
        if self._browser:
            return self._browser
        raise ChromeRuntimeError('`async with` context needed.')

    async def init_browser_tab(self):
        if self._browser:
            raise ChromeRuntimeError('`async with` context is already in use.')
        version = await self.version
        # print(version)
        self._browser = AsyncTab(
            tab_id='browser',
            webSocketDebuggerUrl=version['webSocketDebuggerUrl'],
            chrome=self,
            flatten=False)
        await self._browser.ws_connection.__aenter__()
        self.status = 'connected'
        return self._browser

    def __getitem__(
            self,
            index: Union[int, str] = 0) -> Awaitable[Union[AsyncTab, None]]:
        return self.get_tab(index=index)

    async def __aenter__(self):
        if await self.connect():
            await self.init_browser_tab()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        self.status = 'disconnected'
        if self._req:
            await self._req.close()
        if self.status == 'connected':
            await self._browser.ws_connection.__aexit__(None, None, None)
            self._browser = None

    async def close_browser(self):
        tab0 = await self.get_tab(0)
        if tab0:
            async with tab0():
                try:
                    await tab0.close_browser()
                except RuntimeError:
                    pass

    @property
    def server(self) -> str:
        """return like 'http://127.0.0.1:9222'"""
        if re.match(r'^https?://', self.host):
            prefix = self.host
        else:
            # filled the scheme
            prefix = f"http://{self.host}"
        if self.port:
            return f"{prefix}:{self.port}"
        else:
            return prefix

    async def get_version(self) -> dict:
        """`await self.get_version()`
        /json/version"""
        resp = await self.get_server('/json/version')
        if resp:
            return resp.json()
        else:
            return resp

    @property
    def version(self) -> Awaitable[dict]:
        """`await self.version`
        {'Browser': 'Chrome/77.0.3865.90', 'Protocol-Version': '1.3', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'V8-Version': '7.7.299.11', 'WebKit-Version': '537.36 (@58c425ba843df2918d9d4b409331972646c393dd)', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/b5fbd149-959b-4603-b209-cfd26d66bdc1'}"""
        return self.get_version()

    @property
    def meta(self):
        # same for Sync Chrome
        return self.get_version()

    async def connect(self) -> bool:
        """await self.connect()"""
        self._req = Requests()
        if await self.check_http_ready():
            return True
        else:
            return False

    @property
    def req(self):
        if self._req is None:
            raise ChromeRuntimeError(
                'please use Chrome in `async with` context')
        return self._req

    async def check(self) -> bool:
        """Test http connection to cdp. `await self.check()`
        """
        return bool(await self.check_http_ready()) and (await
                                                        self.check_ws_ready())

    async def check_http_ready(self):
        resp = await self.req.head(self.server,
                                   timeout=self.timeout,
                                   retry=self.retry)
        if not resp:
            self.status = resp.text
        return bool(resp)

    async def check_ws_ready(self):
        try:
            data = await self.browser.browser_version()
            return bool(isinstance(data, dict) and data.get('result'))
        except Exception:
            return False

    @property
    def ok(self):
        """await self.ok"""
        return self.check()

    async def get_server(self, api: str = '') -> NewResponse:
        # maybe return failure request
        url = urljoin(self.server, api)
        resp = await self.req.get(url, timeout=self.timeout, retry=self.retry)
        if not resp:
            self.status = resp.text
        return resp

    async def get_tabs(self, filt_page_type: bool = True) -> List[AsyncTab]:
        """`await self.get_tabs()`.
        cdp url: /json"""
        try:
            r = await self.get_server('/json')
            if r:
                return [
                    AsyncTab(chrome=self, json=rjson, **rjson)
                    for rjson in r.json()
                    if (rjson["type"] == "page" or filt_page_type is not True)
                ]
        except Exception as error:
            logger.error(f'fail to get_tabs from {self.server}, {error!r}')
            raise error
        return []

    async def get_tab(self,
                      index: Union[int, str] = 0) -> Union[AsyncTab, None]:
        """`await self.get_tab(1)` <=> await `(await self.get_tabs())[1]`
        If not exist, return None
        cdp url: /json"""
        tabs = await self.get_tabs()
        try:
            if isinstance(index, int):
                return tabs[index]
            else:
                for tab in tabs:
                    if tab.tab_id == index:
                        return tab
        except IndexError:
            pass
        return None

    @property
    def tabs(self) -> Awaitable[List[AsyncTab]]:
        """`await self.tabs`. tabs[0] is the current activated tab"""
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        return self.get_tabs()

    async def kill(self,
                   timeout: Union[int, float] = None,
                   max_deaths: int = 1) -> None:
        if self.req:
            await self.req.close()
        await async_run(clear_chrome_process,
                        self.port,
                        timeout,
                        max_deaths,
                        host=self.host)

    async def new_tab(self, url: str = "") -> Union[AsyncTab, None]:
        api = f'/json/new?{quote_plus(url)}'
        r = await self.get_server(api)
        if r:
            rjson = r.json()
            tab = AsyncTab(chrome=self, **rjson)
            tab._created_time = int(time.time())
            logger.debug(f"[new_tab] {tab} {rjson}")
            return tab
        else:
            return None

    async def do_tab(self, tab_id: Union[AsyncTab, str],
                     action: str) -> Union[str, bool]:
        ok = False
        if isinstance(tab_id, AsyncTab):
            tab_id = tab_id.tab_id
        r = await self.get_server(f"/json/{action}/{tab_id}")
        if r:
            if action == 'close':
                ok = r.text == "Target is closing"
            elif action == 'activate':
                ok = r.text == "Target activated"
            else:
                ok == r.text
        logger.debug(f"[{action}_tab] <Tab: {tab_id}>: {ok}")
        return ok

    async def activate_tab(self, tab_id: Union[AsyncTab,
                                               str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='activate')

    async def close_tab(self, tab_id: Union[AsyncTab, str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='close')

    async def close_tabs(self,
                         tab_ids: Union[None, List[AsyncTab], List[str]] = None,
                         *args) -> List[Union[str, bool]]:
        if tab_ids is None:
            tab_ids = await self.tabs
        return [await self.close_tab(tab_id) for tab_id in tab_ids]

    def connect_tab(self,
                    index: Union[None, int, str] = 0,
                    auto_close: bool = False,
                    flatten: bool = None):
        '''More easier way to init a connected Tab with `async with`.

        Got a connected Tab object by using `async with chrome.connect_tab(0) as tab::`

            index = 0 means the current tab.
            index = None means create a new tab.
            index = 'http://python.org' means create a new tab with url.
            index = 'F130D0295DB5879791AA490322133AFC' means the tab with this id.

            If auto_close is True: close this tab while exiting context.
'''
        return _SingleTabConnectionManager(chrome=self,
                                           index=index,
                                           auto_close=auto_close,
                                           flatten=flatten)

    def connect_tabs(self, *tabs) -> '_TabConnectionManager':
        '''async with chrome.connect_tabs([tab1, tab2]):.
        or
        async with chrome.connect_tabs(tab1, tab2)'''
        if not tabs:
            raise ChromeValueError(
                f'tabs should not be null, but `{tabs!r}` was given.')
        tab0 = tabs[0]
        if isinstance(tab0, (list, tuple)):
            tabs_todo = tab0
        else:
            tabs_todo = tabs
        return _TabConnectionManager(tabs_todo)

    def get_memory(self, attr='uss', unit='MB'):
        """Only support local Daemon. `uss` is slower than `rss` but useful."""
        return get_memory_by_port(port=self.port,
                                  attr=attr,
                                  unit=unit,
                                  host=self.host)

    def __repr__(self):
        return f"<Chrome({self.status}): {self.port}>"

    def __str__(self):
        return f"<Chrome({self.status}): {self.server}>"

    def __del__(self):
        _exhaust_simple_coro(self.close())

    def create_context(
        self,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
    ) -> 'BrowserContext':
        "create a new Incognito BrowserContext"
        return BrowserContext(
            chrome=self,
            disposeOnDetach=disposeOnDetach,
            proxyServer=proxyServer,
            proxyBypassList=proxyBypassList,
            originsWithUniversalNetworkAccess=originsWithUniversalNetworkAccess,
        )

    def incognito_tab(
        self,
        url: str = 'about:blank',
        width: int = None,
        height: int = None,
        enableBeginFrameControl: bool = None,
        newWindow: bool = None,
        background: bool = None,
        flatten: bool = None,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
    ) -> 'IncognitoTabContext':
        "create a new Incognito tab"
        return IncognitoTabContext(
            chrome=self,
            url=url,
            width=width,
            height=height,
            enableBeginFrameControl=enableBeginFrameControl,
            newWindow=newWindow,
            background=background,
            flatten=flatten,
            disposeOnDetach=disposeOnDetach,
            proxyServer=proxyServer,
            proxyBypassList=proxyBypassList,
            originsWithUniversalNetworkAccess=originsWithUniversalNetworkAccess,
        )


class JavaScriptSnippets(object):

    @staticmethod
    async def add_tip(tab: AsyncTab,
                      text,
                      style=None,
                      max_lines: int = 10,
                      expires: float = None,
                      timeout=NotSet):
        if style is None:
            style = 'position: absolute;max-width: 50%;top: 0.8em; font-size:1.2em; line-height:1.5em; word-break: break-word; right: 0;color: #FF6666; background-color: #ffff99;padding: 1em;z-index:999;display:block;'
        code = f'''
window.ichrome_show_tip_index = (window.ichrome_show_tip_index||0) + 1
window.ichrome_show_tip_array = window.ichrome_show_tip_array || []
window.ichrome_show_tip_array.push(window.ichrome_show_tip_index + '. ' + `{text}`)
window.ichrome_show_tip_array = window.ichrome_show_tip_array.length > {max_lines}?window.ichrome_show_tip_array.slice(window.ichrome_show_tip_array.length - {max_lines}):window.ichrome_show_tip_array
var span = document.querySelector('span#ichrome-show-tip') || document.createElement('span')
span.id = 'ichrome-show-tip'
span.setAttribute('style', '{style}')
span.setAttribute('title', 'double click to hide')
span.setAttribute('ondblclick', "this.style.display = 'none';")
span.innerHTML = window.ichrome_show_tip_array.join('<br>')
document.documentElement.appendChild(span)'''
        if expires:
            code += r'''
setTimeout(() => {
    document.querySelector('span#ichrome-show-tip').style.display='none';
}, %s);
''' % (expires * 1000)
        return await tab.js(code, timeout=timeout)

    @staticmethod
    async def clear_tip(tab: AsyncTab, timeout=NotSet):
        code = '''
window.ichrome_show_tip_index = 0
window.ichrome_show_tip_array = []
var span = document.querySelector('span#ichrome-show-tip') || document.createElement('span')
span.remove()'''
        return await tab.js(code, timeout=timeout)


class WaitContext(object):

    def __init__(self, coro: Coroutine, _auto_cancel=True):
        self._coro = coro
        self._task: asyncio.Task = None
        self._auto_cancel = _auto_cancel

    def __await__(self):
        if self._task:
            return self._task.__await__()

    async def __aenter__(self):
        self._task = asyncio.ensure_future(self._coro)
        return self

    async def __aexit__(self, *_errors):
        if self._auto_cancel and self._task and not self._task.done():
            self._task.cancel()


class EventBuffer(asyncio.Queue):
    _SINGLETON_EVENT_KEY = True

    def __init__(
        self,
        events: List[str],
        tab: AsyncTab,
        timeout: Union[float, int] = None,
        maxsize: int = 0,
        kwargs: Any = None,
        callback: Callable = None,
        context_callbacks: List[Callable] = None,
    ):
        """Event buffer with callback function.

        Args:
            events (List[str]): the list of event names
            tab (AsyncTab): the connected AsyncTab
            timeout (Union[float, int], optional): total timeout for the whole context. Defaults to None.
            maxsize (int, optional): buffer size. Defaults to 0.
            kwargs (Any, optional): some kwargs saved by self. Defaults to None.
            callback (Callable, optional): default callback function for each event. Defaults to None.
            context_callbacks (List[Callable], optional): callback functions [before_startup, after_startup, before_shutdown, after_shutdown]. Defaults to None.

        """
        if isinstance(events, (list, set, tuple)):
            self.events = list(events)
        else:
            raise TypeError
        self.tab = tab
        self.timeout = timeout
        self.kwargs = kwargs
        self.callback = callback
        if context_callbacks is None:
            self.context_callbacks = []
        else:
            self.context_callbacks = context_callbacks
        self._shutdown = False
        super().__init__(maxsize=maxsize)

    def get_timeout(self) -> float:
        if self.timeout:
            return self.start_time + self.timeout - time.time()
        else:
            return None

    async def run_context_callback(self, index):
        if self.context_callbacks:
            try:
                func = self.context_callbacks[index]
                if func:
                    event = [
                        'before_startup', 'after_startup', 'before_shutdown',
                        'after_shutdown'
                    ][index]
                    if asyncio.iscoroutinefunction(func):
                        result = await func(event=event,
                                            tab=self.tab,
                                            buffer=self)
                    else:
                        result = await async_run(
                            func, dict(event=event, tab=self.tab, buffer=self))
                    return result
            except IndexError:
                return

    async def __aenter__(self):
        await self.run_context_callback(0)
        self.start_time = time.time()
        for event_name in self.events:
            if event_name in self.tab._buffers:
                msg = f'Event key duplicated: {event_name}'
                logger.warning(msg)
                if self._SINGLETON_EVENT_KEY:
                    raise ChromeValueError(msg)
            await self.tab.auto_enable(event_name)
            self.tab._buffers[event_name] = self
        await self.run_context_callback(1)
        return self

    async def __aexit__(self, *_):
        await self.run_context_callback(2)
        for event_name in self.events:
            self.tab._buffers.pop(event_name, None)
        await self.run_context_callback(3)

    def __await__(self):
        return self.wait_event().__await__()

    def __aiter__(self):
        return self

    def shutdown(self):
        if not self._shutdown:
            self.put_nowait(None)
            self._shutdown = True

    async def run(self):
        """Run until timeout."""
        async for _ in self:
            pass

    async def wait_event(self):
        while not self._shutdown:
            timeout = self.get_timeout()
            if timeout is None or timeout > 0:
                try:
                    event = await asyncio.wait_for(self.get(), timeout=timeout)
                    if event is None:
                        return
                    if self.callback:
                        if asyncio.iscoroutinefunction(self.callback):
                            result = await self.callback(event=event,
                                                         tab=self.tab,
                                                         buffer=self)
                        else:
                            result = await async_run(
                                self.callback,
                                **dict(event=event, tab=self.tab, buffer=self))
                        return result
                    else:
                        return event
                except asyncio.TimeoutError:
                    pass
            else:
                return

    async def __anext__(self):
        result = await self.wait_event()
        if result:
            return result
        else:
            raise StopAsyncIteration


class FetchBuffer(EventBuffer):
    """Enter and activate Fetch.enable, exit with Fetch.disable. Ensure only one FetchBuffer instance at the same moment.
    https://chromedevtools.github.io/devtools-protocol/tot/Fetch/
    """

    def __init__(
        self,
        events: List[str],
        tab: AsyncTab,
        patterns: List[dict] = None,
        handleAuthRequests=False,
        timeout: Union[float, int] = None,
        maxsize: int = 0,
        kwargs: Any = None,
        callback: Callable = None,
        context_callbacks: List[Callable] = None,
    ):
        self.patterns = patterns or [{'urlPattern': '*'}]
        self.handleAuthRequests = handleAuthRequests
        if not events:
            if handleAuthRequests:
                events = ['Fetch.requestPaused', 'Fetch.authRequired']
            else:
                events = ['Fetch.requestPaused']
        super().__init__(
            events=events,
            tab=tab,
            timeout=timeout,
            maxsize=maxsize,
            kwargs=kwargs,
            callback=callback,
            context_callbacks=context_callbacks,
        )

    async def __aenter__(self):
        await super().__aenter__()
        await self.enable()
        return self

    async def __aexit__(self, *_):
        await self.disable()
        await super().__aexit__(*_)

    async def enable(self):
        return await self.tab.send('Fetch.enable',
                                   patterns=self.patterns,
                                   handleAuthRequests=self.handleAuthRequests)

    async def disable(self):
        return await self.tab.send('Fetch.disable')

    async def wait_event(self):
        while 1:
            data = await super().wait_event()
            if data:
                try:
                    url = data['params']['request']['url']
                    requestId = self.ensure_request_id(data)
                    for pattern in self.patterns:
                        if fnmatchcase(url, pattern['urlPattern']):
                            break
                    else:
                        await self.continueRequest(requestId)
                        continue
                except KeyError:
                    pass
                return data
            else:
                break

    def ensure_request_id(self, data: Union[dict, str]):
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            return data['params']['requestId']
        raise TypeError

    async def fulfillRequest(self,
                             requestId: Union[str, dict],
                             responseCode: int,
                             responseHeaders: List[Dict[str, str]] = None,
                             binaryResponseHeaders: str = None,
                             body: Union[str, bytes] = None,
                             responsePhrase: str = None,
                             kwargs: dict = None,
                             **_kwargs):
        """Fetch.fulfillRequest. Provides response to the request.

        requestId(str): An id the client received in requestPaused event.
        responseCode(int): An HTTP response code.
        responseHeaders(List[Dict[str, str]], optional): Response headers, defaults to None
        binaryResponseHeaders(str, optional): Alternative way of specifying response headers as a \0-separated series of name: value pairs. Prefer the above method unless you need to represent some non-UTF8 values that can't be transmitted over the protocol as text. (Encoded as a base64 string when passed over JSON), defaults to None
        body(Union[str, bytes], optional): A response body. If absent, original response body will be used if the request is intercepted at the response stage and empty body will be used if the request is intercepted at the request stage. (Encoded as a base64 string when passed over JSON), defaults to None. If given as bytes type, will be translate to base64 string automatically.
        responsePhrase(str, optional): A textual representation of responseCode. If absent, a standard phrase matching responseCode is used., defaults to None
        """
        requestId = self.ensure_request_id(requestId)
        if kwargs:
            _kwargs.update(kwargs)
        _kwargs['requestId'] = requestId
        _kwargs['responseCode'] = responseCode
        if isinstance(body, bytes):
            body = b64encode(body).decode('utf-8')
        for key, value in dict(responseHeaders=responseHeaders,
                               binaryResponseHeaders=binaryResponseHeaders,
                               body=body,
                               responsePhrase=responsePhrase).items():
            if value is not None:
                _kwargs[key] = value
        return await self.tab.send('Fetch.fulfillRequest', kwargs=_kwargs)

    async def continueRequest(self,
                              requestId: Union[str, dict],
                              url: str = None,
                              method: str = None,
                              postData: str = None,
                              headers: List[Dict[str, str]] = None,
                              kwargs: dict = None,
                              **_kwargs):
        """Fetch.continueRequest. Continues the request, optionally modifying some of its parameters.

        requestId(str): An id the client received in requestPaused event.
        url(str, optional): If set, the request url will be modified in a way that's not observable by page., defaults to None
        method(str, optional): If set, the request method is overridden., defaults to None
        postData(str, optional): If set, overrides the post data in the request. (Encoded as a base64 string when passed over JSON), defaults to None
        headers(List[Dict[str, str]], optional): If set, overrides the request headers., defaults to None
        kwargs(dict, optional): other params, defaults to None
        """
        requestId = self.ensure_request_id(requestId)
        if kwargs:
            _kwargs.update(kwargs)
        _kwargs['requestId'] = requestId
        for key, value in dict(url=url,
                               method=method,
                               postData=postData,
                               headers=headers).items():
            if value is not None:
                _kwargs[key] = value
        return await self.tab.send('Fetch.continueRequest', kwargs=_kwargs)

    async def continueWithAuth(self,
                               requestId: Union[str, dict],
                               response: str,
                               username: str = None,
                               password: str = None,
                               kwargs: dict = None,
                               **_kwargs):
        """response: Allowed Values: Default, CancelAuth, ProvideCredentials"""
        requestId = self.ensure_request_id(requestId)
        if kwargs:
            _kwargs.update(kwargs)
        _kwargs['requestId'] = requestId
        authChallengeResponse = {}
        for key, value in dict(response=response,
                               username=username,
                               password=password).items():
            if value is not None:
                authChallengeResponse[key] = value
        return await self.tab.send('Fetch.continueWithAuth',
                                   authChallengeResponse=authChallengeResponse,
                                   kwargs=_kwargs)

    async def failRequest(self,
                          requestId: Union[str, dict],
                          errorReason: str,
                          kwargs: dict = None,
                          **_kwargs):
        """Fetch.failRequest. Stop the request.

        Allowed ErrorReason:

        Failed, Aborted, TimedOut, AccessDenied, ConnectionClosed, ConnectionReset, ConnectionRefused, ConnectionAborted, ConnectionFailed, NameNotResolved, InternetDisconnected, AddressUnreachable, BlockedByClient, BlockedByResponse
        """
        requestId = self.ensure_request_id(requestId)
        if kwargs:
            _kwargs.update(kwargs)
        _kwargs['requestId'] = requestId
        _kwargs['errorReason'] = errorReason
        return await self.tab.send('Fetch.failRequest', kwargs=_kwargs)


class BrowserContext:

    def __init__(
        self,
        chrome: AsyncChrome,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
    ):
        self.chrome = chrome
        self.disposeOnDetach = disposeOnDetach
        self.proxyServer = proxyServer
        self.proxyBypassList = proxyBypassList
        self.originsWithUniversalNetworkAccess = originsWithUniversalNetworkAccess
        self.browserContextId = None

        self._need_init_chrome = self.chrome.status == 'init'

    @property
    def browser(self):
        return self.chrome.browser

    def new_tab(
        self,
        url: str = 'about:blank',
        width: int = None,
        height: int = None,
        browserContextId: str = None,
        enableBeginFrameControl: bool = None,
        newWindow: bool = None,
        background: bool = None,
        auto_close: bool = False,
        flatten: bool = None,
    ) -> _SingleTabConnectionManager:
        browserContextId = browserContextId or self.browserContextId
        if not browserContextId:
            raise ChromeRuntimeError('`async with` context needed.')
        _kwargs = dict(
            url=url,
            width=width,
            height=height,
            browserContextId=browserContextId,
            enableBeginFrameControl=enableBeginFrameControl,
            newWindow=newWindow,
            background=background,
        )
        kwargs: dict = {k: v for k, v in _kwargs.items() if v is not None}
        return _SingleTabConnectionManager(chrome=self.chrome,
                                           index=None,
                                           auto_close=auto_close,
                                           target_kwargs=kwargs,
                                           flatten=flatten)

    async def __aenter__(self):
        if self._need_init_chrome:
            await self.chrome.__aenter__()
        kwargs = dict(
            disposeOnDetach=self.disposeOnDetach,
            proxyServer=self.proxyServer,
            proxyBypassList=self.proxyBypassList,
            originsWithUniversalNetworkAccess=self.
            originsWithUniversalNetworkAccess,
        )
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        data = await self.browser.send('Target.createBrowserContext',
                                       kwargs=kwargs)
        self.browserContextId = data['result']['browserContextId']
        return self

    async def __aexit__(self, *_):
        if self.browserContextId:
            try:
                await self.browser.send('Target.disposeBrowserContext')
            except ChromeRuntimeError:
                pass
            self.browserContextId = None
        if self._need_init_chrome:
            await self.chrome.__aexit__()


class IncognitoTabContext:

    def __init__(
        self,
        chrome: AsyncChrome,
        url: str = 'about:blank',
        width: int = None,
        height: int = None,
        enableBeginFrameControl: bool = None,
        newWindow: bool = None,
        background: bool = None,
        flatten: bool = None,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
    ):
        self.target_kwargs: dict = {
            'url': url,
            'width': width,
            'height': height,
            'enableBeginFrameControl': enableBeginFrameControl,
            'newWindow': newWindow,
            'background': background,
            'flatten': flatten,
        }
        self.browser_context = BrowserContext(
            chrome=chrome,
            disposeOnDetach=disposeOnDetach,
            proxyServer=proxyServer,
            proxyBypassList=proxyBypassList,
            originsWithUniversalNetworkAccess=originsWithUniversalNetworkAccess,
        )
        self.connection: _SingleTabConnectionManager = None

    async def __aenter__(self) -> AsyncTab:
        await self.browser_context.__aenter__()
        self.connection = self.browser_context.new_tab(
            url=self.target_kwargs['url'],
            width=self.target_kwargs['width'],
            height=self.target_kwargs['height'],
            enableBeginFrameControl=self.
            target_kwargs['enableBeginFrameControl'],
            newWindow=self.target_kwargs['newWindow'],
            background=self.target_kwargs['background'],
            flatten=self.target_kwargs['flatten'],
        )
        return await self.connection.__aenter__()

    async def __aexit__(self, *_):
        if self.connection:
            await self.connection.__aexit__(*_)
        await self.browser_context.__aexit__(*_)


# alias names
Tab = AsyncTab
Chrome = AsyncChrome
