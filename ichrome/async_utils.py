# -*- coding: utf-8 -*-
# fast and stable connection
import asyncio
import inspect
import json
import time
import traceback
from asyncio.base_futures import _PENDING
from asyncio.futures import Future
from base64 import b64decode
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union
from weakref import WeakValueDictionary

from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.aiohttp_dummy import Requests
from torequests.dummy import NewResponse, _exhaust_simple_coro
from torequests.utils import UA, quote_plus, urljoin

from .base import Tag, TagNotFound, clear_chrome_process, get_memory_by_port
from .logs import logger
"""
Async utils for connections and operations.
[Recommended] Use daemon and async utils with different scripts.
"""

try:
    from asyncio.futures import TimeoutError
except ImportError:
    # for python 3.8+
    from asyncio.exceptions import TimeoutError

NotSet = object()


async def _ensure_awaitable_callback_result(callback_function, result):
    if callable(callback_function):
        callback_result = callback_function(result)
    else:
        return result
    if inspect.isawaitable(callback_result):
        return await callback_result
    else:
        return callback_result


class _TabConnectionManager(object):

    def __init__(self, tabs):
        self.tabs = tabs
        self.ws_connections = set()

    async def __aenter__(self) -> None:
        for tab in self.tabs:
            ws_connection = tab()
            await ws_connection.connect()
            self.ws_connections.add(ws_connection)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for ws_connection in self.ws_connections:
            if not ws_connection._closed:
                await ws_connection.shutdown()


class _WSConnection(object):

    def __init__(self, tab):
        self.tab = tab
        self._closed = None

    def __str__(self):
        return f'<{self.__class__.__name__}: {None if self._closed is None else not self._closed}>'

    async def __aenter__(self):
        return await self.connect()

    async def connect(self):
        """Connect to websocket, and set tab.ws as aiohttp.client_ws.ClientWebSocketResponse."""
        try:
            self.tab.ws = await self.tab.req.session.ws_connect(
                self.tab.webSocketDebuggerUrl, **self.tab.ws_kwargs)
            asyncio.ensure_future(self.tab._recv_daemon())
            logger.debug(
                f'[connected] {self.tab} websocket connection created.')
        except (ClientError, WebSocketError) as err:
            # tab missing(closed)
            logger.error(f'[missing] {self.tab} missing ws connection. {err}')
        # start the daemon background.
        return self.tab

    async def shutdown(self):
        if self.tab.ws and not self.tab.ws.closed:
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


class Tab(GetValueMixin):
    """Tab operations in async environment.

        The timeout variable -- wait for the events::

            NotSet:
                using the self.timeout instead
            None:
                default to self._MAX_WAIT_TIMEOUT, unless you reset the Tab._MAX_WAIT_TIMEOUT -> None for forever
            0:
                no wait
            int / float:
                wait `timeout` seconds
"""
    _log_all_recv = False
    _min_move_interval = 0.05
    _domains_can_be_enabled = {
        'Accessibility', 'Animation', 'ApplicationCache', 'Audits', 'CSS',
        'Cast', 'DOM', 'DOMSnapshot', 'DOMStorage', 'Database',
        'HeadlessExperimental', 'IndexedDB', 'Inspector', 'LayerTree', 'Log',
        'Network', 'Overlay', 'Page', 'Performance', 'Security',
        'ServiceWorker', 'Fetch', 'WebAudio', 'WebAuthn', 'Media', 'Console',
        'Debugger', 'HeapProfiler', 'Profiler', 'Runtime'
    }
    # timeout for recv, for wait_XXX methods
    # You can reset this as None for forever
    _MAX_WAIT_TIMEOUT = 30 * 60
    # timeout for recv, not for wait_XXX methods
    _DEFAULT_RECV_TIMEOUT = 5.0
    # aiohttp ws timeout default to 10.0, here is 5
    _DEFAULT_CONNECT_TIMEOUT = 5.0

    def __init__(self,
                 tab_id: str = None,
                 title: str = None,
                 url: str = None,
                 type: str = None,
                 description: str = None,
                 webSocketDebuggerUrl: str = None,
                 devtoolsFrontendUrl: str = None,
                 json: str = None,
                 chrome: 'Chrome' = None,
                 timeout=NotSet,
                 ws_kwargs: dict = None,
                 default_recv_callback: Callable = None,
                 **kwargs):
        """
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
        :param tab_id: defaults to kwargs.pop('id')
        :type tab_id: str, optional
        :param title: tab title, defaults to None
        :type title: str, optional
        :param url: tab url, binded to self._url, defaults to None
        :type url: str, optional
        :param type: tab type, often be `page` type, defaults to None
        :type type: str, optional
        :param description: tab description, defaults to None
        :type description: str, optional
        :param webSocketDebuggerUrl: ws URL to connect, defaults to None
        :type webSocketDebuggerUrl: str, optional
        :param devtoolsFrontendUrl: devtools UI URL, defaults to None
        :type devtoolsFrontendUrl: str, optional
        :param json: raw Tab JSON, defaults to None
        :type json: str, optional
        :param chrome: the Chrome object which the Tab belongs to, defaults to None
        :type chrome: Chrome, optional
        :param timeout: default recv timeout, defaults to Tab._DEFAULT_RECV_TIMEOUT
        :type timeout: [type], optional
        :param ws_kwargs: kwargs for ws connection, defaults to None
        :type ws_kwargs: dict, optional
        :param default_recv_callback: sync/async function only accept 1 arg of data comes from ws recv, defaults to None
        :type default_recv_callback: Callable, optional
        :raises ValueError: [description]
        """
        tab_id = tab_id or kwargs.pop('id')
        if not tab_id:
            raise ValueError('tab_id should not be null')
        self.tab_id = tab_id
        self.title = title
        self._url = url
        self.type = type
        self.description = description
        self.devtoolsFrontendUrl = devtoolsFrontendUrl
        self.webSocketDebuggerUrl = webSocketDebuggerUrl
        self.json = json
        self.chrome = chrome
        self.timeout = self._DEFAULT_RECV_TIMEOUT if timeout is NotSet else timeout
        self._created_time = self.now
        self.ws_kwargs = ws_kwargs or {}
        self.ws_kwargs.setdefault('timeout', self._DEFAULT_CONNECT_TIMEOUT)
        self._closed = False
        self._message_id = 0
        self.ws = None
        self.default_recv_callback = default_recv_callback
        if self.chrome:
            self.req = self.chrome.req
        else:
            self.req = Requests()
        self._listener = Listener()
        self._enabled_domains: Set[str] = set()

    def __hash__(self):
        return self.tab_id

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __str__(self):
        return f"<Tab({self.status}-{self.chrome!r}): {self.tab_id}>"

    def __repr__(self):
        return f"<Tab({self.status}): {self.tab_id}>"

    def __del__(self):
        if self.ws and not self.ws.closed:
            logger.debug('[unclosed] WSConnection is not closed.')
            asyncio.ensure_future(self.ws.close())

    def ensure_timeout(self, timeout):
        if timeout is NotSet:
            return self.timeout
        elif timeout is None:
            return self._MAX_WAIT_TIMEOUT
        else:
            return timeout

    async def close_browser(self, timeout=NotSet):
        return await self.send('Browser.close', timeout=timeout)

    @property
    def status(self) -> str:
        if self.ws and not self.ws.closed:
            return 'connected'
        return 'disconnected'

    def connect(self) -> _WSConnection:
        '''`async with tab.connect() as tab:`'''
        self._enabled_domains.clear()
        return _WSConnection(self)

    def __call__(self) -> _WSConnection:
        '''`async with tab() as tab:` or just `async with tab():` and reuse `tab` variable.'''
        return self.connect()

    @property
    def msg_id(self):
        self._message_id += 1
        return self._message_id

    @property
    def url(self) -> str:
        """The init url since tab created.
        or using `await self.current_url` for the current url.
        """
        return self._url

    async def refresh_tab_info(self) -> bool:
        r = await self.chrome.get_server('/json')
        if r:
            for tab_info in r.json():
                if tab_info['id'] == self.tab_id:
                    self.title = tab_info['title']
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
        """activate tab with cdp websocket"""
        return await self.send("Page.bringToFront", timeout=timeout)

    async def close(self, timeout=NotSet) -> Union[dict, None]:
        """close tab with cdp websocket"""
        return await self.send("Page.close", timeout=timeout)

    async def crash(self, timeout=NotSet) -> Union[dict, None]:
        return await self.send("Page.crash", timeout=timeout)

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
                # Message size xxxx exceeds limit 4194304: reset the max_msg_size(default=4*1024*1024) in Tab.ws_kwargs
                err_msg = f'Receive the {msg.type!r} message which break the recv daemon: "{msg.data}"'
                logger.error(err_msg)
                raise RuntimeError(err_msg)
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
            await _ensure_awaitable_callback_result(self.default_recv_callback,
                                                    data_dict)
            f = self._listener.find_future(data_dict)
            if f:
                if f._state == _PENDING:
                    f.set_result(data_dict)
                else:
                    del f
        logger.debug(f'[break] {self!r} _recv_daemon loop break.')

    async def send(self,
                   method: str,
                   timeout=NotSet,
                   callback_function: Optional[Callable] = None,
                   kwargs: Dict[str, Any] = None,
                   **_kwargs) -> Union[None, dict]:
        '''Send message to Tab. callback_function only work whlie timeout!=0.
        If timeout is not None: wait for recv event.
        If not force: will check the domain enabled automatically.
        If callback_function: run while received the response msg.
        '''
        timeout = self.ensure_timeout(timeout)
        if kwargs:
            _kwargs.update(kwargs)
        request = {"id": self.msg_id, "method": method, "params": _kwargs}
        try:
            if not self.ws or self.ws.closed:
                raise RuntimeError(f'[closed] {self} ws has been closed')
            logger.debug(f"[send] {self!r} {request}")
            result = await self.ws.send_json(request)
            if timeout != 0:
                # wait for msg filted by id
                event = {"id": request["id"]}
                msg = await self.recv(event,
                                      timeout=timeout,
                                      callback_function=callback_function)
                return msg
            else:
                # timeout == 0, no need wait for response.
                return result
        except (ClientError, WebSocketError, TypeError) as err:
            err_msg = f'{self} [send] msg {request} failed for {err}'
            logger.error(err_msg)
            raise RuntimeError(err_msg)

    async def recv(self,
                   event_dict: dict,
                   timeout=NotSet,
                   callback_function=None) -> Union[dict, None]:
        """Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.

        :param event_dict: dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
        :type event_dict: dict
        :param timeout: await seconds, None for self._MAX_WAIT_TIMEOUT, 0 for 0 seconds.
        :type timeout: float / None, optional
        :param callback_function: event callback_function function accept only one arg(the event dict).
        :type callback_function: callable, optional
        :return: the event dict from websocket recv.
        :rtype: dict
        """
        timeout = self.ensure_timeout(timeout)
        method = event_dict.get('method')
        if method:
            # ensure the domain of method is enabled
            domain = method.split('.', 1)[0]
            await self.enable(domain)
        result = None
        if isinstance(timeout, (float, int)) and timeout <= 0:
            # no wait
            return result
        f = self._listener.register(event_dict)
        try:
            result = await asyncio.wait_for(f, timeout=timeout)
        except TimeoutError:
            logger.debug(f'[timeout] {event_dict} [recv] timeout.')
        finally:
            return await _ensure_awaitable_callback_result(
                callback_function, result)

    @property
    def now(self) -> int:
        return int(time.time())

    async def enable(self, domain: str, force: bool = False, timeout=None):
        '''domain: Network / Page and so on, will send `domain.enable`. Will check for duplicated sendings if not force.'''
        if not force:
            # no need for duplicated enable.
            if domain not in self._domains_can_be_enabled or domain in self._enabled_domains:
                return True
        result = await self.send(f'{domain}.enable', timeout=timeout)
        if result is not None:
            self._enabled_domains.add(domain)
        return result

    async def disable(self, domain: str, force: bool = False, timeout=NotSet):
        '''domain: Network / Page and so on, will send `domain.disable`. Will check for duplicated sendings if not force.'''
        if not force:
            # no need for duplicated enable.
            if domain in self._domains_can_be_enabled or domain not in self._enabled_domains:
                return True
        result = await self.send(f'{domain}.disable', timeout=timeout)
        if result is not None:
            self._enabled_domains.discard(domain)
        return result

    async def get_all_cookies(self, timeout=NotSet):
        """Network.getAllCookies"""
        # {'id': 12, 'result': {'cookies': [{'name': 'test2', 'value': 'test_value', 'domain': 'python.org', 'path': '/', 'expires': -1, 'size': 15, 'httpOnly': False, 'secure': False, 'session': True}]}}
        result = await self.send("Network.getAllCookies", timeout=timeout)
        return self.get_data_value(result, 'result.cookies')

    async def clear_browser_cookies(self, timeout=NotSet):
        """clearBrowserCookies"""
        return await self.send("Network.clearBrowserCookies", timeout=timeout)

    async def clear_cookies(self, timeout=NotSet):
        """clearBrowserCookies. for compatible"""
        return await self.clear_browser_cookies(timeout=timeout)

    async def clear_browser_cache(self, timeout=NotSet):
        """clearBrowserCache"""
        return await self.send("Network.clearBrowserCache", timeout=timeout)

    async def delete_cookies(self,
                             name: str,
                             url: Optional[str] = '',
                             domain: Optional[str] = '',
                             path: Optional[str] = '',
                             timeout=NotSet):
        """deleteCookies by name, with url / domain / path."""
        if not any((url, domain)):
            raise ValueError(
                'At least one of the url and domain needs to be specified')
        return await self.send("Network.deleteCookies",
                               name=name,
                               url=url,
                               domain=domain,
                               path=path,
                               timeout=timeout)

    async def get_cookies(self,
                          urls: Union[List[str], str] = None,
                          timeout=NotSet) -> List:
        """get cookies of urls."""
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
                         timeout=NotSet):
        """name [string] Cookie name.
value [string] Cookie value.
url [string] The request-URI to associate with the setting of the cookie. This value can affect the default domain and path values of the created cookie.
domain [string] Cookie domain.
path [string] Cookie path.
secure [boolean] True if cookie is secure.
httpOnly [boolean] True if cookie is http-only.
sameSite [CookieSameSite] Cookie SameSite type.
expires [TimeSinceEpoch] Cookie expiration date, session cookie if not set"""
        if not any((url, domain)):
            raise ValueError(
                'At least one of the url and domain needs to be specified')
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
                               force=False,
                               **kwargs)

    async def get_current_url(self, timeout=NotSet) -> str:
        url = await self.get_variable("window.location.href", timeout=timeout)
        return url or ""

    @property
    def current_url(self):
        return self.get_current_url()

    async def get_current_title(self, timeout=NotSet) -> str:
        title = await self.get_variable("document.title", timeout=timeout)
        return title or ""

    @property
    def current_title(self) -> Awaitable[str]:
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
        result = await self.get_frame_tree(timeout=timeout)
        return self.get_data_value(result,
                                   value_path='result.frameTree.frame.id')

    @property
    def frame_tree(self):
        return self.get_frame_tree()

    async def get_frame_tree(self, timeout=NotSet):
        return await self.send('Page.getFrameTree', timeout=timeout)

    async def stop_loading_page(self, timeout=0):
        '''Page.stopLoading'''
        return await self.send("Page.stopLoading", timeout=timeout)

    async def wait_loading(self,
                           timeout=NotSet,
                           callback_function: Optional[Callable] = None,
                           timeout_stop_loading=False) -> bool:
        '''Page.loadEventFired event for page loaded.
        If page loaded event catched, return True.'''
        data = await self.wait_event("Page.loadEventFired",
                                     timeout=timeout,
                                     callback_function=callback_function)
        if data is None and timeout_stop_loading:
            await self.stop_loading_page()
            return False
        return bool(data)

    async def wait_page_loading(self,
                                timeout=NotSet,
                                callback_function: Optional[Callable] = None,
                                timeout_stop_loading=False):
        return self.wait_loading(timeout=timeout,
                                 callback_function=callback_function,
                                 timeout_stop_loading=timeout_stop_loading)

    async def wait_event(
        self,
        event_name: str,
        timeout=NotSet,
        callback_function: Optional[Callable] = None,
        filter_function: Optional[Callable] = None
    ) -> Union[dict, None, Any]:
        """Similar to self.recv, but has the filter_function to distinct duplicated method of event."""
        timeout = self.ensure_timeout(timeout)
        start_time = time.time()
        result = None
        while 1:
            if timeout is not None and time.time() - start_time > timeout:
                break
            # avoid same method but different event occured, use filter_function
            event = {"method": event_name}
            _result = await self.recv(event, timeout=timeout)
            if filter_function:
                try:
                    ok = await _ensure_awaitable_callback_result(
                        filter_function, _result)
                    if ok:
                        result = _result
                        break
                except Exception:
                    continue
            elif _result:
                result = _result
                break
        return await _ensure_awaitable_callback_result(callback_function,
                                                       result)

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
            timeout = timeout - start_time
        if response_body:
            # set the data value
            if request_dict:
                data = await self.get_response_body(
                    request_dict['params']['requestId'],
                    timeout=timeout,
                    wait_loading=True)
                request_dict['data'] = self.get_data_value(data, 'result.body')
            elif isinstance(request_dict, dict):
                request_dict['data'] = None
        return await _ensure_awaitable_callback_result(callback_function,
                                                       request_dict)

    async def wait_request(self,
                           filter_function: Optional[Callable] = None,
                           callback_function: Optional[Callable] = None,
                           timeout=NotSet):
        '''Network.requestWillBeSent. To wait a special request filted by function, then run the callback_function(request_dict).

        Often used for HTTP packet capture:

            `await tab.wait_request(filter_function=lambda r: print(r), timeout=10)`

        WARNING: requestWillBeSent event fired do not mean the response is ready,
        should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
'''
        request_dict = await self.wait_event("Network.requestWillBeSent",
                                             filter_function=filter_function,
                                             timeout=timeout)
        return await _ensure_awaitable_callback_result(callback_function,
                                                       request_dict)

    async def wait_request_loading(self,
                                   request_dict: Union[None, dict, str],
                                   timeout=NotSet):

        def request_id_filter(event):
            return event["params"]["requestId"] == request_id

        request_id = self._ensure_request_id(request_dict)
        return await self.wait_event('Network.loadingFinished',
                                     timeout=timeout,
                                     filter_function=request_id_filter)

    async def wait_loading_finished(self, request_dict: dict, timeout=NotSet):
        return await self.wait_request_loading(request_dict=request_dict,
                                               timeout=timeout)

    @staticmethod
    def _ensure_request_id(request_id: Union[None, dict, str]):
        if request_id is None:
            return None
        if isinstance(request_id, str):
            return request_id
        elif isinstance(request_id, dict):
            return Tab.get_data_value(request_id, 'params.requestId')
        else:
            raise TypeError(
                f"request type should be None or dict or str, but given `{type(request_id)}`"
            )

    async def get_response(
            self,
            request_dict: Union[None, dict, str],
            timeout=NotSet,
            wait_loading: bool = False,
    ) -> Union[dict, None]:
        '''Network.getResponseBody.
        return demo:

                {'id': 2, 'result': {'body': 'JSON source code', 'base64Encoded': False}}

        WARNING: some ajax request need to await tab.wait_request_loading(request_dict) for
        loadingFinished (or sleep some secs), so set the wait_loading=True.'''
        start_time = time.time()
        request_id = self._ensure_request_id(request_dict)
        if request_id is None:
            return None
        timeout = self.ensure_timeout(timeout)
        if wait_loading:
            # ensure the request loaded
            await self.wait_request_loading(request_id, timeout=timeout)
            if timeout is not None:
                timeout = timeout - (time.time() - start_time)
                if timeout <= 0:
                    return None
        result = await self.send("Network.getResponseBody",
                                 requestId=request_id,
                                 timeout=timeout)
        return result

    async def get_response_body(self,
                                request_dict: Union[None, dict, str],
                                timeout=NotSet,
                                wait_loading=False) -> Union[dict, None]:
        """For tab.wait_request's callback_function. This will await loading before getting resonse body."""
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
        '''
        # if 'Referer' in headers or 'referer' in headers:
        #     logger.warning('`Referer` is not valid header, please use the `referrer` arg of set_url')'''
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
        logger.debug(f'[set_ua] {self!r} userAgent => {userAgent}')
        data = await self.send('Network.setUserAgentOverride',
                               userAgent=userAgent,
                               acceptLanguage=acceptLanguage,
                               platform=platform,
                               timeout=timeout)
        return data

    async def goto_history(self, entryId: int = 0, timeout=NotSet) -> bool:
        result = await self.send('Page.navigateToHistoryEntry',
                                 entryId=entryId,
                                 timeout=timeout)
        return self.check_error('goto_history', result, entryId=entryId)

    async def get_history_entry(self,
                                index: int = None,
                                relative_index: int = None,
                                timeout=NotSet):
        result = await self.get_history_list(timeout=timeout)
        if result:
            if index is None:
                index = result['currentIndex'] + relative_index
                return result['entries'][index]
            elif relative_index is None:
                return result['entries'][index]
            else:
                raise ValueError(
                    f'index and relative_index should not be both None.')

    async def history_back(self, timeout=NotSet):
        return await self.goto_history_relative(relative_index=-1,
                                                timeout=timeout)

    async def history_forward(self, timeout=NotSet):
        return await self.goto_history_relative(relative_index=1,
                                                timeout=timeout)

    async def goto_history_relative(self,
                                    relative_index: int = None,
                                    timeout=NotSet):
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
        """return dict: {'currentIndex': 0, 'entries': [{'id': 1, 'url': 'about:blank', 'userTypedURL': 'about:blank', 'title': '', 'transitionType': 'auto_toplevel'}, {'id': 7, 'url': 'http://3.p.cn/', 'userTypedURL': 'http://3.p.cn/', 'title': 'Not Found', 'transitionType': 'typed'}, {'id': 9, 'url': 'http://p.3.cn/', 'userTypedURL': 'http://p.3.cn/', 'title': '', 'transitionType': 'typed'}]}}"""
        result = await self.send('Page.getNavigationHistory', timeout=timeout)
        return self.get_data_value(result, value_path='result', default={})

    async def reset_history(self, timeout=NotSet) -> bool:
        result = await self.send('Page.resetNavigationHistory', timeout=timeout)
        return self.check_error('reset_history', result)

    async def set_url(self,
                      url: Optional[str] = None,
                      referrer: Optional[str] = None,
                      timeout=NotSet,
                      timeout_stop_loading: bool = False) -> bool:
        """
        Navigate the tab to the URL. If stop loading occurs, return False.
        """
        logger.debug(f'[set_url] {self!r} url => {url}')
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
        return bool(data and (await self.wait_loading(
            timeout=timeout, timeout_stop_loading=timeout_stop_loading)))

    async def js(self,
                 javascript: str,
                 value_path=None,
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
                                 expression=javascript)
        logger.debug(
            f'[js] {self!r} insert js `{javascript}`, received: {result}.')
        if value_path:
            return self.get_data_value(result, value_path)
        return result

    async def handle_dialog(self,
                            accept=True,
                            promptText=None,
                            timeout=NotSet) -> bool:
        kwargs = {'timeout': timeout, 'accept': accept}
        if promptText is not None:
            kwargs['promptText'] = promptText
        result = await self.send('Page.handleJavaScriptDialog', **kwargs)
        return self.check_error('handle_dialog',
                                result,
                                accept=accept,
                                promptText=promptText)

    async def wait_tags(self,
                        cssselector: str,
                        max_wait_time: Optional[float] = None,
                        interval: float = 1,
                        timeout=NotSet) -> Union[None, List[Tag]]:
        '''Wait until the tags is ready or max_wait_time used up, sometimes it is more useful than wait loading.
        cssselector: css querying the Tags.
        interval: checking interval for while loop.
        max_wait_time: if time used up, return [].
        timeout: timeout seconds for sending a msg.

        If max_wait_time used up: return [].
        elif querySelectorAll runs failed, return None.
        else: return List[Tag]
        '''
        tags = []
        TIMEOUT_AT = time.time() + (max_wait_time or self._MAX_WAIT_TIMEOUT)
        while TIMEOUT_AT > time.time():
            tags = await self.querySelectorAll(cssselector=cssselector,
                                               timeout=timeout)
            if tags:
                break
            await asyncio.sleep(interval)
        return tags

    async def querySelector(self,
                            cssselector: str,
                            action: Union[None, str] = None,
                            timeout=NotSet):
        return await self.querySelectorAll(cssselector=cssselector,
                                           index=0,
                                           action=action,
                                           timeout=timeout)

    async def querySelectorAll(self,
                               cssselector: str,
                               index: Union[None, int, str] = None,
                               action: Union[None, str] = None,
                               timeout=NotSet):
        """CDP DOM domain is quite heavy both computationally and memory wise, use js instead. return List[Tag], Tag, TagNotFound.
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
            response_items_str = (await self.js(
                javascript, timeout=timeout,
                value_path='result.result.value')) or ''
            items = json.loads(response_items_str)
            result = [Tag(**kws) for kws in items]
            if isinstance(index, int):
                if result:
                    return result[index]
                else:
                    return TagNotFound()
            else:
                return result
        except Exception as e:
            logger.error(f"querySelectorAll error: {e!r}, response: {response}")
            return None

    async def inject_js(self, *args, **kwargs):
        # for compatible
        return await self.inject_js_url(*args, **kwargs)

    async def inject_js_url(self,
                            url,
                            timeout=None,
                            retry=0,
                            verify=False,
                            **requests_kwargs) -> Union[dict, None]:
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
        """
        await tab.click("#sc_hdu>li>a") # click first node's link.
        await tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
        """
        return await self.querySelectorAll(cssselector,
                                           index=index,
                                           action=action,
                                           timeout=timeout)

    async def get_element_clip(self, cssselector: str, scale=1, timeout=NotSet):
        """Element.getBoundingClientRect"""
        js_str = 'JSON.stringify(document.querySelector(`%s`).getBoundingClientRect())' % cssselector
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

    async def get_bounding_client_rect(self,
                                       cssselector: str,
                                       scale=1,
                                       timeout=NotSet):
        return await self.get_element_clip(cssselector=cssselector,
                                           scale=scale,
                                           timeout=timeout)

    async def screenshot_element(self,
                                 cssselector: str,
                                 scale=1,
                                 format: str = 'png',
                                 quality: int = 100,
                                 fromSurface: bool = True,
                                 save_path=None,
                                 timeout=NotSet):
        clip = await self.get_element_clip(cssselector, scale=scale)
        return await self.screenshot(format=format,
                                     quality=quality,
                                     clip=clip,
                                     fromSurface=fromSurface,
                                     save_path=save_path,
                                     timeout=timeout)

    async def screenshot(self,
                         format: str = 'png',
                         quality: int = 100,
                         clip: dict = None,
                         fromSurface: bool = True,
                         save_path=None,
                         timeout=NotSet):
        """Page.captureScreenshot.

        :param format: Image compression format (defaults to png)., defaults to 'png'
        :type format: str, optional
        :param quality: Compression quality from range [0..100], defaults to None. (jpeg only).
        :type quality: int, optional
        :param clip: Capture the screenshot of a given region only. defaults to None, means whole page.
        :type clip: dict, optional
        :param fromSurface: Capture the screenshot from the surface, rather than the view. Defaults to true.
        :type fromSurface: bool, optional

        clip's keys: x, y, width, height, scale"""

        def save(save_path, base64_img):
            with open(save_path, 'wb') as f:
                f.write(b64decode(base64_img))

        kwargs = dict(format=format, quality=quality, fromSurface=fromSurface)
        if clip:
            kwargs['clip'] = clip
        result = await self.send('Page.captureScreenshot',
                                 timeout=timeout,
                                 callback_function=None,
                                 force=False,
                                 **kwargs)
        base64_img = self.get_data_value(result, value_path='result.data')
        if save_path and base64_img:
            await asyncio.get_running_loop().run_in_executor(
                save, save_path, base64_img)
        return base64_img

    async def add_js_onload(self, source: str, **kwargs) -> str:
        '''Page.addScriptToEvaluateOnNewDocument, return the identifier [str].'''
        data = await self.send('Page.addScriptToEvaluateOnNewDocument',
                               source=source,
                               **kwargs)
        return self.get_data_value(data, value_path='result.identifier') or ''

    async def remove_js_onload(self, identifier: str, timeout=NotSet) -> bool:
        '''Page.removeScriptToEvaluateOnNewDocument, return whether the identifier exist.'''
        result = await self.send('Page.removeScriptToEvaluateOnNewDocument',
                                 identifier=identifier,
                                 timeout=timeout)
        return self.check_error('remove_js_onload',
                                result,
                                identifier=identifier)

    async def get_value(self, name: str, timeout=NotSet):
        """name or expression"""
        return await self.get_variable(name, timeout=timeout)

    async def get_variable(self, name: str, timeout=NotSet):
        """variable or expression"""
        # using JSON to keep value type
        return await self.js(name,
                             timeout=timeout,
                             value_path='result.result.value')

    async def get_screen_size(self, timeout=NotSet):
        return await self.get_value(
            '[window.screen.width, window.screen.height]', timeout=timeout)

    async def get_page_size(self, timeout=NotSet):
        return await self.get_value(
            "[window.innerWidth||document.documentElement.clientWidth||document.querySelector('body').clientWidth,window.innerHeight||document.documentElement.clientHeight||document.querySelector('body').clientHeight]",
            timeout=timeout)

    async def keyboard_send(self,
                            *,
                            type='char',
                            timeout=NotSet,
                            string=None,
                            **kwargs):
        '''type: keyDown, keyUp, rawKeyDown, char.

        kwargs:
            text, unmodifiedText, keyIdentifier, code, key...

        https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchKeyEvent'''
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

    async def mouse_click(self, x, y, button='left', count=1, timeout=NotSet):
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
        return await self.send('Input.dispatchMouseEvent',
                               type="mousePressed",
                               x=x,
                               y=y,
                               button=button,
                               clickCount=count,
                               timeout=timeout)

    async def mouse_release(self, x, y, button='left', count=0, timeout=NotSet):
        return await self.send('Input.dispatchMouseEvent',
                               type="mouseReleased",
                               x=x,
                               y=y,
                               button=button,
                               clickCount=count,
                               timeout=timeout)

    @staticmethod
    def get_smooth_steps(target_x, target_y, start_x, start_y, steps_count=30):

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
        # move mouse smoothly only if duration > 0.
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
            steps = [(target_x, target_y)]
        for x, y in steps:
            if duration:
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


class OffsetMoveWalker(object):
    __slots__ = ('path', 'start_x', 'start_y', 'tab', 'timeout')

    def __init__(self, start_x, start_y, tab: Tab, timeout=NotSet):
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

    def __init__(self, start_x, start_y, tab: Tab, button='left', timeout=None):
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


class Listener(object):

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
        return key

    def register(self, event_dict: dict):
        '''Listener will register a event_dict, such as {'id': 1} or {'method': 'Page.loadEventFired'}, maybe the dict doesn't has key [method].'''
        f: Future = Future()
        key = self._arg_to_key(event_dict)
        self._registered_futures[key] = f
        return f

    def find_future(self, event_dict):
        key = self._arg_to_key(event_dict)
        return self._registered_futures.get(key)


class Chrome(GetValueMixin):
    _DEFAULT_CONNECT_TIMEOUT = 2

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 9222,
                 timeout: int = None,
                 retry: int = 1):
        self.host = host
        self.port = port
        self.timeout = timeout or self._DEFAULT_CONNECT_TIMEOUT
        self.retry = retry
        self.status = 'init'
        self._req = None

    def __getitem__(self, index: int) -> Awaitable[Tab]:
        assert isinstance(index, int), 'only support int index'
        return self.get_tab(index=index)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.__del__()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close_browser(self):
        tab0 = await self.get_tab(0)
        if tab0:
            async with tab0():
                await tab0.send('Browser.close')

    @property
    def server(self) -> str:
        """return like 'http://127.0.0.1:9222'"""
        return f"http://{self.host}:{self.port}"

    async def get_version(self) -> dict:
        """`await self.get_version()`
        /json/version"""
        resp = await self.get_server('/json/version')
        if resp:
            return resp.json()
        else:
            raise resp.error

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
        if await self.check():
            return True
        else:
            return False

    @property
    def req(self):
        if self._req is None:
            raise RuntimeError('please use Chrome in `async with`')
        return self._req

    async def check(self) -> bool:
        """Test http connection to cdp. `await self.check()`
        """
        r = await self.get_server()
        if r:
            self.status = 'connected'
            logger.debug(f'[{self.status}] {self} checked.')
            return True
        else:
            self.status = 'disconnected'
            logger.debug(f'[{self.status}] {self} checked.')
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

    async def get_tabs(self, filt_page_type: bool = True) -> List[Tab]:
        """`await self.get_tabs()`.
        cdp url: /json"""
        try:
            r = await self.get_server('/json')
            if r:
                return [
                    Tab(chrome=self, json=rjson, **rjson)
                    for rjson in r.json()
                    if (rjson["type"] == "page" or filt_page_type is not True)
                ]
        except Exception:
            logger.error(
                f'fail to get_tabs {self.server}, {traceback.format_exc()}')
        return []

    async def get_tab(self, index: int = 0) -> Union[Tab, None]:
        """`await self.get_tab(1)` <=> await `(await self.get_tabs())[1]`
        If not exist, return None
        cdp url: /json"""
        tabs = await self.get_tabs()
        try:
            return tabs[index]
        except IndexError:
            return None

    @property
    def tabs(self) -> Awaitable[List[Tab]]:
        """`await self.tabs`. tabs[0] is the current activated tab"""
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        return self.get_tabs()

    async def kill(self,
                   timeout: Union[int, float] = None,
                   max_deaths: int = 1) -> None:
        if self.req:
            await self.req.close()
        await asyncio.get_running_loop().run_in_executor(
            None, clear_chrome_process, self.port, timeout, max_deaths)

    async def new_tab(self, url: str = "") -> Union[Tab, None]:
        api = f'/json/new?{quote_plus(url)}'
        r = await self.get_server(api)
        if r:
            rjson = r.json()
            tab = Tab(chrome=self, **rjson)
            tab._created_time = tab.now
            logger.debug(f"[new_tab] {tab} {rjson}")
            return tab
        else:
            return None

    async def do_tab(self, tab_id: Union[Tab, str],
                     action: str) -> Union[str, bool]:
        ok = False
        if isinstance(tab_id, Tab):
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

    async def activate_tab(self, tab_id: Union[Tab, str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='activate')

    async def close_tab(self, tab_id: Union[Tab, str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='close')

    async def close_tabs(self,
                         tab_ids: Union[None, List[Tab], List[str]] = None,
                         *args) -> List[Union[str, bool]]:
        if tab_ids is None:
            tab_ids = await self.tabs
        return [await self.close_tab(tab_id) for tab_id in tab_ids]

    def connect_tabs(self, *tabs) -> '_TabConnectionManager':
        '''async with chrome.connect_tabs([tab1, tab2]):.
        or
        async with chrome.connect_tabs(tab1, tab2)'''
        if not tabs:
            raise ValueError('tabs should not be null.')
        tab0 = tabs[0]
        if isinstance(tab0, (list, tuple)):
            tabs_todo = tab0
        else:
            tabs_todo = tabs
        return _TabConnectionManager(tabs_todo)

    def get_memory(self, attr='uss', unit='MB'):
        """Only support local Daemon. `uss` is slower than `rss` but useful."""
        return get_memory_by_port(port=self.port, attr=attr, unit=unit)

    def __repr__(self):
        return f"<Chrome({self.status}): {self.port}>"

    def __str__(self):
        return f"<Chrome({self.status}): {self.server}>"

    async def close(self):
        if self.status == 'closed':
            return
        if self.req:
            await self.req.close()
        self.status = 'closed'

    def __del__(self):
        _exhaust_simple_coro(self.close())
