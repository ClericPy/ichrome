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
from typing import Awaitable, Callable, List, Optional, Union
from weakref import WeakValueDictionary

from aiofiles import open as aopen
from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.aiohttp_dummy import Requests
from torequests.dummy import NewResponse, _exhaust_simple_coro
from torequests.utils import UA, quote_plus, urljoin

from .base import Tag, clear_chrome_process
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


async def ensure_awaitable_result(callback_function, result):
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
                self.tab.webSocketDebuggerUrl,
                timeout=self.tab.timeout,
                **self.tab.ws_kwargs)
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
    def get_data_value(item, path: str = 'result.result.value', default=None):
        """default path is for js response dict"""
        if not item:
            return default
        try:
            for key in path.split('.'):
                item = item.__getitem__(key)
            return item
        except (KeyError, TypeError):
            return default

    @classmethod
    def check_error(cls, name, result, path='error.message', **kwargs):
        error = cls.get_data_value(result, path=path)
        if error:
            logger.info(f'{name} failed: {kwargs}. result: {result}')
        return not error


class Tab(GetValueMixin):
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

    def __init__(self,
                 tab_id=None,
                 title=None,
                 url=None,
                 webSocketDebuggerUrl=None,
                 json=None,
                 chrome=None,
                 timeout=5,
                 ws_kwargs=None,
                 **kwargs):
        tab_id = tab_id or kwargs.pop('id')
        if not tab_id:
            raise ValueError('tab_id should not be null')
        self.tab_id = tab_id
        self.title = title
        self._url = url
        self.webSocketDebuggerUrl = webSocketDebuggerUrl
        self.json = json
        self.chrome = chrome
        self.timeout = timeout
        self._created_time = None
        self.ws_kwargs = ws_kwargs or {}
        self._closed = False
        self._message_id = 0
        self.ws = None
        if self.chrome:
            self.req = self.chrome.req
        else:
            self.req = Requests()
        self._listener = Listener()
        self._enabled_domains = set()

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

    async def close_browser(self):
        return await self.send('Browser.close')

    @property
    def status(self) -> str:
        if self.ws and not self.ws.closed:
            return 'connected'
        return 'disconnected'

    def connect(self) -> _WSConnection:
        '''`async with tab.connect:`'''
        self._enabled_domains.clear()
        return _WSConnection(self)

    def __call__(self) -> _WSConnection:
        '''`async with tab():`'''
        return self.connect()

    @property
    def msg_id(self):
        self._message_id += 1
        return self._message_id

    @property
    def url(self) -> str:
        """The init url since tab created.
        `await self.current_url` for the current url.
        """
        return self._url

    async def refresh_tab_info(self) -> bool:
        for tab in await self.chrome.tabs:
            if tab.tab_id == self.tab_id:
                self.tab_id = tab.tab_id
                self.title = tab.title
                self._url = tab.url
                self.webSocketDebuggerUrl = tab.webSocketDebuggerUrl
                self.json = tab.json
                return True
        return False

    async def activate_tab(self) -> Union[str, bool]:
        """activate tab with chrome http endpoint"""
        return await self.chrome.activate_tab(self)

    async def close_tab(self) -> Union[str, bool]:
        """close tab with chrome http endpoint"""
        return await self.chrome.close_tab(self)

    async def activate(self) -> Union[dict, None]:
        """activate tab with cdp websocket"""
        return await self.send("Page.bringToFront")

    async def close(self) -> Union[dict, None]:
        """close tab with cdp websocket"""
        return await self.send("Page.close")

    async def crash(self) -> Union[dict, None]:
        return await self.send("Page.crash")

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
                break
            if msg.type != WSMsgType.TEXT:
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
            f = self._listener.find_future(data_dict)
            if f:
                if f._state == _PENDING:
                    f.set_result(data_dict)
                else:
                    del f
        logger.debug(f'[break] {self!r} _recv_daemon loop break.')

    async def send(self,
                   method: str,
                   timeout: Union[int, float] = None,
                   callback_function: Optional[Callable] = None,
                   force: bool = False,
                   **kwargs) -> Union[None, dict]:
        timeout = self.timeout if timeout is None else timeout
        if not force:
            # not force, will check lots of scene
            domain = method.split('.', 1)[0]
            if method.endswith('.enable'):
                # check domain if enabled or not, avoid duplicated enable.
                if domain in self._enabled_domains:
                    logger.debug(f'{domain} no need enable twice.')
                    return None
                else:
                    # set force to True
                    return await self.enable(domain,
                                             force=True,
                                             timeout=timeout)
            elif method.endswith('.disable'):
                if domain not in self._enabled_domains:
                    logger.debug(f'{domain} no need disable twice.')
                    return None
                else:
                    # set force to True
                    return await self.disable(domain,
                                              force=True,
                                              timeout=timeout)
            timeout = await self._ensure_enable_and_timeout(domain,
                                                            timeout=timeout)

        request = {"method": method, "params": kwargs}
        request["id"] = self.msg_id
        if not self.ws or self.ws.closed:
            logger.error(
                f'[closed] {self} ws has been closed, ignore send {request}')
            return None
        try:
            logger.debug(f"[send] {self!r} {request}")
            await self.ws.send_json(request)
            if timeout <= 0:
                # not care for response
                return None
            event = {"id": request["id"]}
            msg = await self.recv(event,
                                  timeout=timeout,
                                  callback_function=callback_function)
            return msg
        except (ClientError, WebSocketError, TypeError) as err:
            logger.error(f'{self} [send] msg failed for {err}')
            return None

    async def recv(self,
                   event_dict: dict,
                   timeout: Union[int, float] = None,
                   callback_function=None) -> Union[dict, None]:
        """Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.

        :param event_dict: dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
        :type event_dict: dict
        :param timeout: await seconds, None for permanent, 0 for 0 seconds.
        :type timeout: float / None, optional
        :param callback_function: event callback_function function accept only one arg(the event dict).
        :type callback_function: callable, optional
        :return: the event dict from websocket recv.
        :rtype: dict
        """
        method = event_dict.get('method')
        if method:
            # ensure the domain of method is enabled
            domain = method.split('.', 1)[0]
            timeout = await self._ensure_enable_and_timeout(domain,
                                                            timeout=timeout)
        result = None
        timeout = self.timeout if timeout is None else timeout
        if timeout <= 0:
            return result
        f = self._listener.register(event_dict)
        try:
            result = await asyncio.wait_for(f, timeout=timeout)
        except TimeoutError:
            logger.debug(f'[timeout] {event_dict} [recv] timeout.')
        finally:
            return await ensure_awaitable_result(callback_function, result)

    @property
    def now(self) -> int:
        return int(time.time())

    async def _ensure_enable_and_timeout(self,
                                         domain: str,
                                         timeout=None) -> Union[float, int]:
        '''return a timeout num.
        ::

                if domain is enabled:
                    return timeout
                else:
                    await enable
                    return left timeout
        '''
        if domain in self._enabled_domains or domain not in self._domains_can_be_enabled:
            return timeout
        else:
            start_time = time.time()
            for tries in range(3):
                if await self.enable(domain, force=True, timeout=timeout):
                    break
            timeout = timeout - (time.time() - start_time)
            if timeout <= 0:
                return 0
            return timeout

    async def enable(self, domain: str, force: bool = False, timeout=None):
        '''domain: Network / Page and so on, will send `domain.enable`. Will check for duplicated sendings.'''
        if domain not in self._domains_can_be_enabled:
            logger.warning(
                f'{domain} not in valid domains {self._domains_can_be_enabled}')
        result = await self.send(f'{domain}.enable',
                                 force=force,
                                 timeout=timeout)
        if result is not None:
            self._enabled_domains.add(domain)
        return result

    async def disable(self, domain: str, force: bool = False, timeout=None):
        '''domain: Network / Page and so on, will send `domain.disable`. Will check for duplicated sendings.'''
        if domain not in self._domains_can_be_enabled:
            logger.warning(
                f'{domain} not in valid domains {self._domains_can_be_enabled}')
        result = await self.send(f'{domain}.disable',
                                 force=force,
                                 timeout=timeout)
        if result is not None:
            self._enabled_domains.discard(domain)
        return result

    async def get_all_cookies(self, timeout: Union[int, float] = None):
        """Network.getAllCookies"""
        # {'id': 12, 'result': {'cookies': [{'name': 'test2', 'value': 'test_value', 'domain': 'python.org', 'path': '/', 'expires': -1, 'size': 15, 'httpOnly': False, 'secure': False, 'session': True}]}}
        result = (await self.send("Network.getAllCookies",
                                  timeout=timeout)) or {}
        return result['result']['cookies']

    async def clear_browser_cookies(self, timeout: Union[int, float] = None):
        """clearBrowserCookies"""
        return await self.send("Network.clearBrowserCookies", timeout=timeout)

    async def clear_cookies(self, timeout: Union[int, float] = None):
        """clearBrowserCookies. for compatible"""
        return await self.clear_browser_cookies(timeout)

    async def clear_browser_cache(self, timeout: Union[int, float] = None):
        """clearBrowserCache"""
        return await self.send("Network.clearBrowserCache", timeout=timeout)

    async def delete_cookies(self,
                             name: str,
                             url: Optional[str] = '',
                             domain: Optional[str] = '',
                             path: Optional[str] = '',
                             timeout: Union[int, float] = None):
        """deleteCookies by name, with url / domain / path."""
        if not any((url, domain)):
            raise ValueError(
                'At least one of the url and domain needs to be specified')
        return await self.send(
            "Network.deleteCookies",
            name=name,
            url=url,
            domain=domain,
            path=path,
            timeout=timeout or self.timeout,
        )

    async def get_cookies(self,
                          urls: Union[List[str], str] = None,
                          timeout: Union[int, float] = None) -> List:
        """get cookies of urls."""
        if urls:
            if isinstance(urls, str):
                urls = [urls]
            urls = list(urls)
            result = await self.send("Network.getCookies",
                                     urls=urls,
                                     timeout=None)
        else:
            result = await self.send("Network.getCookies", timeout=None)
        result = result or {}
        try:
            return result["result"]["cookies"]
        except Exception:
            return []

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
                         timeout: Union[int, float] = None):
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
        # expires = expires or int(time.time())
        kwargs = dict(name=name,
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

    async def get_current_url(self) -> str:
        url = await self.get_variable("window.location.href")
        return url or ""

    @property
    def current_url(self):
        return self.get_current_url()

    async def get_current_title(self) -> str:
        title = await self.get_variable("document.title")
        return title or ""

    @property
    def current_title(self) -> Awaitable[str]:
        return self.get_current_title()

    @property
    def current_html(self) -> Awaitable[str]:
        return self.html

    async def get_html(self) -> str:
        """return html from `document.documentElement.outerHTML`"""
        html = await self.get_variable('document.documentElement.outerHTML')
        return html or ""

    @property
    def html(self) -> Awaitable[str]:
        """`await tab.html`. return html from `document.documentElement.outerHTML`"""
        return self.get_html()

    async def set_html(self, html: str, frame_id: str = None, timeout=None):
        start_time = time.time()
        if frame_id is None:
            frame_id = await self.get_page_frame_id(timeout=timeout)
        timeout = (timeout or self.timeout) - (time.time() - start_time)
        if timeout <= 0:
            return None
        if frame_id is None:
            return await self.js(f'document.write(`{html}`)', timeout=timeout)
        else:
            return await self.send('Page.setDocumentContent',
                                   html=html,
                                   frameId=frame_id,
                                   timeout=timeout)

    async def get_page_frame_id(self, timeout=None):
        result = await self.get_frame_tree(timeout=timeout)
        return self.get_data_value(result, path='result.frameTree.frame.id')

    @property
    def frame_tree(self):
        return self.get_frame_tree()

    async def get_frame_tree(self, timeout=None):
        return await self.send('Page.getFrameTree', timeout=timeout)

    async def stop_loading_page(self, timeout=0):
        '''Page.stopLoading'''
        return await self.send("Page.stopLoading", timeout=timeout)

    async def wait_loading(self,
                           timeout: Union[int, float] = None,
                           callback_function: Optional[Callable] = None,
                           timeout_stop_loading=False) -> Union[dict, None]:
        '''Page.loadEventFired event for page loaded.'''
        data = await self.wait_event("Page.loadEventFired",
                                     timeout=timeout,
                                     callback_function=callback_function)
        if data is None and timeout_stop_loading:
            await self.stop_loading_page()
        return data

    async def wait_page_loading(self,
                                timeout: Union[int, float] = None,
                                callback_function: Optional[Callable] = None,
                                timeout_stop_loading=False):
        return self.wait_loading(timeout=timeout,
                                 callback_function=callback_function,
                                 timeout_stop_loading=timeout_stop_loading)

    async def wait_event(
            self,
            event_name: str,
            timeout: Union[int, float] = None,
            callback_function: Optional[Callable] = None,
            filter_function: Optional[Callable] = None) -> Union[dict, None]:
        """Similar to self.recv, but has the filter_function to distinct duplicated method of event."""
        timeout = self.timeout if timeout is None else timeout
        start_time = time.time()
        result = None
        while 1:
            if time.time() - start_time > timeout:
                break
            # avoid same method but different event occured, use filter_function
            event = {"method": event_name}
            _result = await self.recv(event, timeout=timeout)
            if filter_function:
                try:
                    ok = await ensure_awaitable_result(filter_function, _result)
                    if ok:
                        result = _result
                        break
                except Exception:
                    continue
            elif _result:
                result = _result
                break
        return await ensure_awaitable_result(callback_function, result)

    async def wait_response(self,
                            filter_function: Optional[Callable] = None,
                            callback_function: Optional[Callable] = None,
                            timeout: Union[int, float] = None):
        '''wait a special response filted by function, then run the callback_function.

        Sometimes the request fails to be sent, so use the `tab.wait_request` instead.'''
        request_dict = await self.wait_event("Network.responseReceived",
                                             filter_function=filter_function,
                                             timeout=timeout)
        return await ensure_awaitable_result(callback_function, request_dict)

    async def wait_request(self,
                           filter_function: Optional[Callable] = None,
                           callback_function: Optional[Callable] = None,
                           timeout: Union[int, float] = None):
        '''Network.requestWillBeSent. To wait a special request filted by function, then run the callback_function(request_dict).

        Often used for HTTP packet capture:

            `await tab.wait_request(filter_function=lambda r: print(r), timeout=10)`

        WARNING: requestWillBeSent event fired do not mean the response is ready,
        should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
'''
        request_dict = await self.wait_event("Network.requestWillBeSent",
                                             filter_function=filter_function,
                                             timeout=timeout)
        return await ensure_awaitable_result(callback_function, request_dict)

    async def wait_request_loading(self,
                                   request_dict: Union[None, dict, str],
                                   timeout: Union[int, float] = None):

        def request_id_filter(event):
            return event["params"]["requestId"] == request_id

        request_id = self._ensure_request_id(request_dict)
        return await self.wait_event('Network.loadingFinished',
                                     timeout=timeout,
                                     filter_function=request_id_filter)

    async def wait_loading_finished(self,
                                    request_dict: dict,
                                    timeout: Union[int, float] = None):
        return await self.wait_request_loading(request_dict=request_dict,
                                               timeout=timeout)

    @staticmethod
    def _ensure_request_id(request_id: Union[None, dict, str]):
        if request_id is None:
            return None
        if isinstance(request_id, str):
            return request_id
        elif isinstance(request_id, dict):
            return request_id['params']['requestId']
        else:
            raise TypeError(
                f"request type should be None or dict or str, but given `{type(request_id)}`"
            )

    async def get_response(
            self,
            request_dict: Union[None, dict, str],
            timeout: Union[int, float] = None,
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
        if wait_loading:
            # ensure the request loaded
            await self.wait_request_loading(request_id, timeout=timeout)
            timeout = (timeout or self.timeout) - (time.time() - start_time)
        if timeout < 0:
            timeout = 0
        result = await self.send("Network.getResponseBody",
                                 requestId=request_id,
                                 timeout=timeout)
        return result

    async def get_response_body(self,
                                request_dict: Union[None, dict, str],
                                timeout: Union[int, float] = None,
                                wait_loading=False) -> Union[dict, None]:
        """For tab.wait_request's callback_function. This will await loading before getting resonse body."""
        result = await self.get_response(request_dict,
                                         timeout=timeout,
                                         wait_loading=wait_loading)
        return self.get_data_value(result, path='result.body', default='')

    async def get_request_post_data(
            self,
            request_dict: Union[None, dict, str],
            timeout: Union[int, float] = None) -> Union[str, None]:
        """Get the post data of the POST request. No need for wait_request_loading."""
        request_id = self._ensure_request_id(request_dict)
        if request_id is None:
            return None
        result = await self.send("Network.getRequestPostData",
                                 requestId=request_id,
                                 timeout=timeout)
        return self.get_data_value(result, path='result.postData')

    async def reload(self,
                     ignoreCache: bool = False,
                     scriptToEvaluateOnLoad: str = None,
                     timeout: Union[None, float, int] = None):
        """Reload the page.

        ignoreCache: If true, browser cache is ignored (as if the user pressed Shift+refresh).
        scriptToEvaluateOnLoad: If set, the script will be injected into all frames of the inspected page after reload.

        Argument will be ignored if reloading dataURL origin."""
        if timeout is None:
            timeout = self.timeout
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

    async def set_headers(self,
                          headers: dict,
                          timeout: Union[float, int] = None):
        '''
        # if 'Referer' in headers or 'referer' in headers:
        #     logger.warning('`Referer` is not valid header, please use the `referrer` arg of set_url')'''
        logger.info(f'[set_headers] {self!r} headers => {headers}')
        data = await self.send('Network.setExtraHTTPHeaders',
                               headers=headers,
                               timeout=timeout)
        return data

    async def set_ua(self,
                     userAgent: str,
                     acceptLanguage: Optional[str] = '',
                     platform: Optional[str] = '',
                     timeout: Union[float, int] = None):
        logger.info(f'[set_ua] {self!r} userAgent => {userAgent}')
        data = await self.send('Network.setUserAgentOverride',
                               userAgent=userAgent,
                               acceptLanguage=acceptLanguage,
                               platform=platform,
                               timeout=timeout)
        return data

    async def goto_history(self, entryId: int = 0, timeout=None):
        result = await self.send('Page.navigateToHistoryEntry',
                                 entryId=entryId,
                                 timeout=timeout)
        return self.check_error('goto_history', result, entryId=entryId)

    async def get_history_entry(self,
                                index: int = None,
                                relative_index: int = None,
                                timeout=None):
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

    async def history_back(self, timeout=None):
        return await self.goto_history_relative(relative_index=-1)

    async def history_forward(self, timeout=None):
        return await self.goto_history_relative(relative_index=1)

    async def goto_history_relative(self,
                                    relative_index: int = None,
                                    timeout=None):
        try:
            entry = await self.get_history_entry(relative_index=relative_index,
                                                 timeout=timeout)
        except IndexError:
            return None
        entry_id = self.get_data_value(entry, 'id')
        if entry_id is not None:
            return await self.goto_history(entryId=entry_id, timeout=timeout)
        return False

    async def get_history_list(self, timeout=None) -> dict:
        """return dict: {'currentIndex': 0, 'entries': [{'id': 1, 'url': 'about:blank', 'userTypedURL': 'about:blank', 'title': '', 'transitionType': 'auto_toplevel'}, {'id': 7, 'url': 'http://3.p.cn/', 'userTypedURL': 'http://3.p.cn/', 'title': 'Not Found', 'transitionType': 'typed'}, {'id': 9, 'url': 'http://p.3.cn/', 'userTypedURL': 'http://p.3.cn/', 'title': '', 'transitionType': 'typed'}]}}"""
        result = await self.send('Page.getNavigationHistory', timeout=timeout)
        return self.get_data_value(result, path='result', default={})

    async def reset_history(self, timeout=None):
        result = await self.send('Page.resetNavigationHistory', timeout=timeout)
        return self.check_error('reset_history', result)

    async def set_url(self,
                      url: Optional[str] = None,
                      referrer: Optional[str] = None,
                      timeout: Union[float, int] = None,
                      timeout_stop_loading: bool = True):
        """
        Navigate the tab to the URL
        """
        if timeout is None:
            timeout = self.timeout
        logger.debug(f'[set_url] {self!r} url => {url}')
        start_load_ts = self.now
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
            data = await self.send("Page.reload", timeout=timeout)
        time_passed = self.now - start_load_ts
        real_timeout = max((timeout - time_passed, 0))
        await self.wait_loading(timeout=real_timeout,
                                timeout_stop_loading=timeout_stop_loading)
        return data

    async def js(self,
                 javascript: str,
                 timeout: Union[float, int] = None) -> Union[None, dict]:
        """
        Evaluate JavaScript on the page.
        `js_result = await tab.js('document.title', timeout=10)`
        js_result:
        {'id': 18, 'result': {'result': {'type': 'string', 'value': 'Welcome to Python.org'}}}
        if timeout: return None
        """
        logger.debug(f'[js] {self!r} insert js `{javascript}`.')
        return await self.send("Runtime.evaluate",
                               timeout=timeout,
                               expression=javascript)

    async def handle_dialog(self, accept=True, promptText=None, timeout=None):
        kwargs = {'timeout': timeout, 'accept': accept}
        if promptText is not None:
            kwargs['promptText'] = promptText
        result = await self.send('Page.handleJavaScriptDialog', **kwargs)
        return self.check_error('handle_dialog',
                                result,
                                accept=accept,
                                promptText=promptText)

    async def querySelectorAll(self,
                               cssselector: str,
                               index: Union[None, int, str] = None,
                               action: Union[None, str] = None,
                               timeout: Union[float, int] = None):
        """CDP DOM domain is quite heavy both computationally and memory wise, use js instead. return List[Tag], Tag, None.
        If index is not None, will return the tag_list[index]
        else return the tag list.
        tab.querySelectorAll("#sc_hdu>li>a", index=2, action="removeAttribute('href')")
        for i in tab.querySelectorAll("#sc_hdu>li"):
        """
        if "'" in cssselector:
            cssselector = cssselector.replace("'", "\\'")
        if index is None:
            index = "null"
        else:
            index = int(index)
        if action:
            action = f"item.result=el.{action} || '';item.result=item.result.toString()"

        else:
            action = ""
        javascript = """
            var elements = document.querySelectorAll('%s');

            var result = []
            var index_filter = %s

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
                    result: "",
                    attributes: {}
                }
                for (const attr of el.attributes) {
                    item.attributes[attr.name] = attr.value
                }
                try {
                    %s
                } catch (error) {
                }
                result.push(item)
            }
            JSON.stringify(result)
        """ % (
            cssselector,
            index,
            action,
        )
        response = None
        try:
            response = (await self.js(javascript, timeout=timeout)) or {}
            response_items_str = self.get_data_value(response, default='')
            items = json.loads(response_items_str)
            result = [Tag(**kws) for kws in items]
            if isinstance(index, int):
                if result:
                    return result[0]
                else:
                    return None
            else:
                return result
        except Exception as e:
            logger.error(f"querySelectorAll error: {e}, response: {response}")
            if isinstance(index, int):
                return None
            return []

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

    async def click(
            self,
            cssselector: str,
            index: int = 0,
            action: str = "click()",
            timeout: Union[float, int] = None) -> Union[List[Tag], Tag, None]:
        """
        await tab.click("#sc_hdu>li>a") # click first node's link.
        await tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
        """
        return await self.querySelectorAll(cssselector,
                                           index=index,
                                           action=action,
                                           timeout=timeout)

    async def get_element_clip(self, cssselector: str, scale=1):
        """Element.getBoundingClientRect"""
        js_str = 'JSON.stringify(document.querySelector(`' + cssselector + '`).getBoundingClientRect())'
        rect = self.get_data_value(await self.js(js_str))
        if rect:
            try:
                rect = json.loads(rect)
                rect['scale'] = scale
                return rect
            except (TypeError, KeyError, json.JSONDecodeError):
                pass

    async def get_bounding_client_rect(self, cssselector: str, scale=1):
        return await self.get_element_clip(cssselector=cssselector, scale=scale)

    async def screenshot_element(self,
                                 cssselector: str,
                                 scale=1,
                                 format: str = 'png',
                                 quality: int = 100,
                                 fromSurface: bool = True,
                                 save_path=None):
        clip = await self.get_element_clip(cssselector, scale=scale)
        return await self.screenshot(format=format,
                                     quality=quality,
                                     clip=clip,
                                     fromSurface=fromSurface,
                                     save_path=save_path)

    async def screenshot(self,
                         format: str = 'png',
                         quality: int = 100,
                         clip: dict = None,
                         fromSurface: bool = True,
                         save_path=None,
                         timeout=None):
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
        kwargs = dict(format=format, quality=quality, fromSurface=fromSurface)
        if clip:
            kwargs['clip'] = clip
        result = await self.send('Page.captureScreenshot',
                                 timeout=timeout,
                                 callback_function=None,
                                 force=False,
                                 **kwargs)
        base64_img = self.get_data_value(result, path='result.data')
        if save_path and base64_img:
            async with aopen(save_path, 'wb') as f:
                await f.write(b64decode(base64_img))
        return base64_img

    async def add_js_onload(self, source: str, **kwargs) -> str:
        '''Page.addScriptToEvaluateOnNewDocument, return the identifier [str].'''
        data = await self.send('Page.addScriptToEvaluateOnNewDocument',
                               source=source,
                               **kwargs)
        return self.get_data_value(data, path='result.identifier') or ''

    async def remove_js_onload(self, identifier: str, timeout=None):
        '''Page.removeScriptToEvaluateOnNewDocument, return whether the identifier exist.'''
        result = await self.send('Page.removeScriptToEvaluateOnNewDocument',
                                 identifier=identifier,
                                 timeout=timeout)
        return self.check_error('remove_js_onload',
                                result,
                                identifier=identifier)

    async def get_value(self, name: str):
        """name or expression"""
        return await self.get_variable(name)

    async def get_variable(self, name: str):
        """name or expression"""
        # using JSON to keep value type
        result = await self.js('JSON.stringify({"%s": %s})' % ('key', name))
        value = self.get_data_value(result)
        if value:
            try:
                return json.loads(value)['key']
            except (TypeError, KeyError, json.JSONDecodeError):
                logger.debug(f'get_variable failed: {result}')

    async def get_screen_size(self):
        return await self.get_value(
            '[window.screen.width, window.screen.height]')

    async def get_page_size(self):
        return await self.get_value(
            "[window.innerWidth||document.documentElement.clientWidth||document.querySelector('body').clientWidth,window.innerHeight||document.documentElement.clientHeight||document.querySelector('body').clientHeight]"
        )

    async def keyboard_send(self,
                            *,
                            type='char',
                            timeout=None,
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

    async def mouse_click(self, x, y, button='left', count=1, timeout=None):
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

    async def mouse_press(self, x, y, button='left', count=0, timeout=None):
        return await self.send('Input.dispatchMouseEvent',
                               type="mousePressed",
                               x=x,
                               y=y,
                               button=button,
                               clickCount=count,
                               timeout=timeout)

    async def mouse_release(self, x, y, button='left', count=0, timeout=None):
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
                         timeout=None):
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
                             timeout=None):
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

    def mouse_move_rel_chain(self, start_x, start_y, timeout=None):
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
                         timeout=None):
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
                             timeout=None):
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
                             timeout=None):
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

    def __init__(self, start_x, start_y, tab: Tab, timeout=None):
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

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 9222,
                 timeout: int = 2,
                 retry: int = 1):
        self.host = host
        self.port = port
        self.timeout = timeout
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
                    Tab(chrome=self, **rjson)
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
