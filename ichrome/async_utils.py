# fast and stable connection
import asyncio
import inspect
import json
import re
import time
import traceback
from asyncio.base_futures import _PENDING
from asyncio.futures import Future
from base64 import b64decode
from functools import partial
from typing import Any, Awaitable, Callable, List, Optional, Union
from weakref import WeakValueDictionary

from aiofiles import open as aopen
from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.dummy import NewResponse, Pool, Requests
from torequests.utils import UA, quote_plus, urljoin

from .base import ChromeDaemon, Tag
from .logs import logger

"""
Async utils for connections and operations.
[Recommended] Use daemon and async utils with different scripts.
"""

try:
    from asyncio.futures import TimeoutError
except ImportError:
    # for python 3.8
    from asyncio.exceptions import TimeoutError


def get_data_value(item, default=None, path: str = 'result.result.value'):
    if not item:
        return None
    try:
        for key in path.split('.'):
            item = item.__getitem__(key)
        return item
    except (KeyError, TypeError):
        return default


class AsyncChromeDaemon:
    __doc__ = ChromeDaemon.__doc__

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
            timeout=2,
            debug=False,
    ):
        self.kwargs = dict(
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
        )

    async def __aenter__(self):
        loop = asyncio.get_running_loop()
        self.daemon = await loop.run_in_executor(
            None, partial(ChromeDaemon, **self.kwargs))
        return self.daemon

    async def __aexit__(self, *args, **kwargs):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.daemon.__exit__)


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
        return f'<{self.__class__.__name__}: {not self._closed}>'

    async def __aenter__(self):
        return await self.connect()

    async def connect(self):
        """Connect to websocket, and set tab.ws as aiohttp.client_ws.ClientWebSocketResponse."""
        try:
            session = await self.tab.req.session
            self.tab.ws = await session.ws_connect(
                self.tab.webSocketDebuggerUrl,
                timeout=self.tab.timeout,
                **self.tab.ws_kwargs)
            asyncio.ensure_future(self.tab._recv_daemon(), loop=self.tab.loop)
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


class Tab(object):
    _log_all_recv = False
    get_data_value = get_data_value
    _min_move_interval = 0.05

    def __init__(self,
                 tab_id=None,
                 title=None,
                 url=None,
                 webSocketDebuggerUrl=None,
                 json=None,
                 chrome=None,
                 timeout=5,
                 ws_kwargs=None,
                 loop=None,
                 **kwargs):
        tab_id = tab_id or kwargs.pop('id')
        if not tab_id:
            raise ValueError('tab_id should not be null')
        self.loop = loop
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
            self.req = Requests(loop=self.loop)
        self._listener = Listener()
        self._enabled_methods = set()

    def __hash__(self):
        return self.tab_id

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __str__(self):
        return f"<Tab({self.status}{self.chrome!r}): {self.tab_id}>"

    def __repr__(self):
        return f"<Tab({self.status}): {self.tab_id}>"

    def __del__(self):
        if self.ws and not self.ws.closed:
            logger.debug('[unclosed] WSConnection is not closed.')
            asyncio.ensure_future(self.ws.close(), loop=self.loop)

    async def close_browser(self):
        return await self.send('Browser.close')

    @property
    def status(self) -> str:
        status = 'disconnected'
        if self.ws and not self.ws.closed:
            status = 'connected'
        return status

    def connect(self) -> _WSConnection:
        '''`async with tab.connect:`'''
        self._enabled_methods.clear()
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
        await self.enable('Page')
        return await self.send("Page.bringToFront")

    async def close(self) -> Union[dict, None]:
        """close tab with cdp websocket"""
        await self.enable('Page')
        return await self.send("Page.close")

    async def crash(self) -> Union[dict, None]:
        await self.enable('Page')
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

    def _check_duplicated_on_off(self, method: str) -> bool:
        """ignore nonsense enable / disable method.
        return True means need to send.
        return False means ignore sending operations."""
        if not re.match(r'^\w+\.(enable|disable)$', method):
            return True
        function, action = method.split('.')
        if action == 'enable':
            if function in self._enabled_methods:
                # ignore
                return False
            else:
                # update _enabled_methods
                self._enabled_methods.add(function)
                return True
        elif action == 'disable':
            if function in self._enabled_methods:
                # update _enabled_methods
                self._enabled_methods.discard(function)
                return True
            else:
                # ignore
                return False
        else:
            return True

    async def send(self,
                   method: str,
                   timeout: Union[int, float] = None,
                   callback_function: Optional[Callable] = None,
                   check_duplicated_on_off: bool = False,
                   **kwargs) -> Union[None, dict]:
        request = {"method": method, "params": kwargs}
        if check_duplicated_on_off and not self._check_duplicated_on_off(
                method):
            logger.debug(f'{method} sended before, ignore. {self}')
            return None
        request["id"] = self.msg_id
        if not self.ws or self.ws.closed:
            logger.error(
                f'[closed] {self} ws has been closed, ignore send {request}')
            return None
        try:
            timeout = self.timeout if timeout is None else timeout
            logger.debug(f"[send] {self!r} {request}")
            await self.ws.send_json(request)
            if timeout <= 0:
                # not care for response
                return None
            event = {"id": request["id"]}
            msg = await self.recv(
                event, timeout=timeout, callback_function=callback_function)
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

    async def enable(self, name: str, force: bool = False):
        '''name: Network / Page and so on, will send `Name.enable`. Will check for duplicated sendings.'''
        return await self.send(
            f'{name}.enable', check_duplicated_on_off=not force)

    async def disable(self, name: str, force: bool = False):
        '''name: Network / Page and so on, will send `Name.disable`. Will check for duplicated sendings.'''
        return await self.send(
            f'{name}.disable', check_duplicated_on_off=not force)

    async def get_all_cookies(self, timeout: Union[int, float] = None):
        """Network.getAllCookies"""
        await self.enable('Network')
        # {'id': 12, 'result': {'cookies': [{'name': 'test2', 'value': 'test_value', 'domain': 'python.org', 'path': '/', 'expires': -1, 'size': 15, 'httpOnly': False, 'secure': False, 'session': True}]}}
        result = (await self.send("Network.getAllCookies",
                                  timeout=timeout)) or {}
        return result['result']['cookies']

    async def clear_browser_cookies(self, timeout: Union[int, float] = None):
        """clearBrowserCookies"""
        await self.enable('Network')
        return await self.send("Network.clearBrowserCookies", timeout=timeout)

    async def clear_browser_cache(self, timeout: Union[int, float] = None):
        """clearBrowserCache"""
        await self.enable('Network')
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
        await self.enable('Network')
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
        await self.enable('Network')
        if urls:
            if isinstance(urls, str):
                urls = [urls]
            urls = list(urls)
            result = await self.send(
                "Network.getCookies", urls=urls, timeout=None)
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
        kwargs = dict(
            name=name,
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
        await self.enable('Network')
        return await self.send(
            "Network.setCookie",
            timeout=timeout or self.timeout,
            callback_function=None,
            check_duplicated_on_off=False,
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

    async def wait_loading(self,
                           timeout: Union[int, float] = None,
                           callback_function: Optional[Callable] = None,
                           timeout_stop_loading=False) -> Union[dict, None]:
        data = await self.wait_event(
            "Page.loadEventFired",
            timeout=timeout,
            callback_function=callback_function)
        if data is None and timeout_stop_loading:
            await self.send("Page.stopLoading", timeout=0)
        return data

    async def wait_page_loading(self,
                                timeout: Union[int, float] = None,
                                callback_function: Optional[Callable] = None,
                                timeout_stop_loading=False):
        return self.wait_loading(
            timeout=timeout,
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
        '''wait a special response filted by function, then run the callback_function'''
        await self.enable('Network')
        request_dict = await self.wait_event(
            "Network.responseReceived",
            filter_function=filter_function,
            timeout=timeout)
        return await ensure_awaitable_result(callback_function, request_dict)

    async def wait_request_loading(self,
                                   request_dict: dict,
                                   timeout: Union[int, float] = None):

        def request_id_filter(event):
            return event["params"]["requestId"] == request_id

        request_id = request_dict["params"]["requestId"]
        return await self.wait_event(
            'Network.loadingFinished',
            timeout=timeout,
            filter_function=request_id_filter)

    async def wait_loading_finished(self,
                                    request_dict: dict,
                                    timeout: Union[int, float] = None):
        return await self.wait_request_loading(
            request_dict=request_dict, timeout=timeout)

    async def get_response(
            self,
            request_dict: dict,
            timeout: Union[int, float] = None,
    ) -> Union[dict, None]:
        '''{'id': 30, 'result': {'body': 'xxxxxxxxx', 'base64Encoded': False}}.
        WARNING: some ajax request need to wait_request_loading before loadingFinished.'''
        if request_dict is None:
            return None
        await self.enable('Network')
        request_id = request_dict["params"]["requestId"]
        resp = await self.send(
            "Network.getResponseBody", requestId=request_id, timeout=timeout)
        return resp

    async def reload(self, timeout: Union[None, float, int] = None):
        """
        Reload the page
        """
        if timeout is None:
            timeout = self.timeout
        return await self.set_url(timeout=timeout)

    async def set_headers(self,
                          headers: dict,
                          timeout: Union[float, int] = None):
        '''
        # if 'Referer' in headers or 'referer' in headers:
        #     logger.warning('`Referer` is not valid header, please use the `referrer` arg of set_url')'''
        logger.info(f'[set_headers] {self!r} headers => {headers}')
        await self.enable('Network')
        data = await self.send(
            'Network.setExtraHTTPHeaders', headers=headers, timeout=timeout)
        return data

    async def set_ua(self,
                     userAgent: str,
                     acceptLanguage: Optional[str] = '',
                     platform: Optional[str] = '',
                     timeout: Union[float, int] = None):
        logger.info(f'[set_ua] {self!r} userAgent => {userAgent}')
        await self.enable('Network')
        data = await self.send(
            'Network.setUserAgentOverride',
            userAgent=userAgent,
            acceptLanguage=acceptLanguage,
            platform=platform,
            timeout=timeout)
        return data

    async def set_url(self,
                      url: Optional[str] = None,
                      referrer: Optional[str] = None,
                      timeout: Union[float, int] = None):
        """
        Navigate the tab to the URL
        """
        if timeout is None:
            timeout = self.timeout
        logger.debug(f'[set_url] {self!r} url => {url}')
        start_load_ts = self.now
        await self.enable('Page')
        if url:
            self._url = url
            if referrer is None:
                data = await self.send(
                    "Page.navigate", url=url, timeout=timeout)
            else:
                data = await self.send(
                    "Page.navigate",
                    url=url,
                    referrer=referrer,
                    timeout=timeout)
        else:
            data = await self.send("Page.reload", timeout=timeout)
        time_passed = self.now - start_load_ts
        real_timeout = max((timeout - time_passed, 0))
        await self.wait_loading(timeout=real_timeout, timeout_stop_loading=True)
        return data

    async def js(self, javascript: str,
                 timeout: Union[float, int] = None) -> Union[None, dict]:
        """
        Evaluate JavaScript on the page.
        `js_result = await tab.js('document.title', timeout=10)`
        js_result:
        {'id': 18, 'result': {'result': {'type': 'string', 'value': 'Welcome to Python.org'}}}
        if timeout: return None
        """
        await self.enable('Runtime')
        logger.debug(f'[js] {self!r} insert js `{javascript}`.')
        return await self.send(
            "Runtime.evaluate", timeout=timeout, expression=javascript)

    async def querySelectorAll(
            self,
            cssselector: str,
            index: Union[None, int, str] = None,
            action: Union[None, str] = None,
            timeout: Union[float, int] = None) -> Union[List[Tag], Tag, None]:
        """CDP DOM domain is quite heavy both computationally and memory wise, use js instead.
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
            response_items_str = get_data_value(response, '')
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

    async def inject_js_url(self,
                            url,
                            timeout=None,
                            retry=0,
                            verify=False,
                            **requests_kwargs) -> Union[dict, None]:
        r = await self.req.get(
            url,
            timeout=timeout,
            retry=retry,
            headers={'User-Agent': UA.Chrome},
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
        return await self.querySelectorAll(
            cssselector, index=index, action=action, timeout=timeout)

    async def get_element_clip(self, cssselector: str, scale=1):
        """Element.getBoundingClientRect"""
        rect = get_data_value(
            await self.js('JSON.stringify(document.querySelector(`' +
                          cssselector + '`).getBoundingClientRect())'))
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
        return await self.screenshot(
            format=format,
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
        await self.enable('Page')
        kwargs = dict(format=format, quality=quality, fromSurface=fromSurface)
        if clip:
            kwargs['clip'] = clip
        result = await self.send(
            'Page.captureScreenshot',
            timeout=timeout,
            callback_function=None,
            check_duplicated_on_off=False,
            **kwargs)
        base64_img = get_data_value(result, None, path='result.data')
        if save_path and base64_img:
            async with aopen(save_path, 'wb') as f:
                await f.write(b64decode(base64_img))
        return base64_img

    async def add_js_onload(self, source, **kwargs):
        '''Page.addScriptToEvaluateOnNewDocument'''
        return await self.send(
            'Page.addScriptToEvaluateOnNewDocument', source=source, **kwargs)

    async def get_value(self, name: str):
        """name or expression"""
        return await self.get_variable(name)

    async def get_variable(self, name: str):
        """name or expression"""
        # using JSON to keep value type
        result = await self.js('JSON.stringify({"%s": %s})' % ('key', name))
        value = get_data_value(result)
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

    async def keyboard_send(self, type='char', timeout=None, **kwargs):
        '''type: keyDown, keyUp, rawKeyDown, char.

        kwargs:
            text, unmodifiedText, keyIdentifier, code, key...

        https://chromedevtools.github.io/devtools-protocol/tot/Input#method-dispatchMouseEvent'''
        return await self.send(
            'Input.dispatchKeyEvent', type=type, timeout=timeout, **kwargs)

    async def mouse_click(self, x, y, button='left', count=1, timeout=None):
        await self.mouse_press(
            x=x, y=y, button=button, count=count, timeout=timeout)
        return await self.mouse_release(
            x=x, y=y, button=button, count=1, timeout=timeout)

    async def mouse_press(self, x, y, button='left', count=0, timeout=None):
        return await self.send(
            'Input.dispatchMouseEvent',
            type="mousePressed",
            x=x,
            y=y,
            button=button,
            clickCount=count,
            timeout=timeout)

    async def mouse_release(self, x, y, button='left', count=0, timeout=None):
        return await self.send(
            'Input.dispatchMouseEvent',
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
        await self.enable('Input')
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
            steps = self.get_smooth_steps(
                target_x, target_y, start_x, start_y, steps_count=steps_count)
        else:
            steps = [(target_x, target_y)]
        for x, y in steps:
            if duration:
                await asyncio.sleep(interval)
            await self.send(
                'Input.dispatchMouseEvent',
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
        await self.mouse_move(
            start_x=start_x,
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
        await self.enable('Input')
        await self.mouse_press(start_x, start_y, button=button, timeout=timeout)
        await self.mouse_move(
            target_x, target_y, duration=duration, timeout=timeout)
        await self.mouse_release(
            target_x, target_y, button=button, timeout=timeout)
        return (target_x, target_y)

    async def mouse_drag_rel(self,
                             start_x,
                             start_y,
                             offset_x,
                             offset_y,
                             button='left',
                             duration=0,
                             timeout=None):
        return await self.mouse_drag(
            start_x,
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
        return OffsetDragWalker(
            start_x, start_y, tab=self, button=button, timeout=timeout)


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
            await self.tab.mouse_move_rel(
                x,
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
        await self.tab.mouse_press(
            self.start_x,
            self.start_y,
            button=self.button,
            timeout=self.timeout)
        while self.path:
            x, y, duration = self.path.pop(0)
            await self.tab.mouse_move_rel(
                x,
                y,
                self.start_x,
                self.start_y,
                duration=duration,
                timeout=self.timeout)
            self.start_x += x
            self.start_y += y
        await self.tab.mouse_release(
            self.start_x,
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


class InvalidRequests(object):

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            'Chrome has not connected. `await chrome.connect()` before request.'
        )

    def __bool__(self):
        return False


class Chrome:
    get_data_value = get_data_value

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 9222,
                 timeout: int = 2,
                 retry: int = 1,
                 loop: Optional[asyncio.AbstractEventLoop] = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry = retry
        self.loop = loop
        self.status = 'init'
        self.req = InvalidRequests()

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

    async def connect(self) -> bool:
        """await self.connect()"""
        self.req = Requests(loop=self.loop)
        if await self.check():
            return True
        else:
            return False

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

    async def get_server(self, api: str = '') -> 'NewResponse':
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

    async def kill(self, timeout: Union[int, float] = None,
                   max_deaths: int = 1) -> None:
        if self.req:
            loop = self.req.loop
            await self.req.close()
        else:
            loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            Pool(1), ChromeDaemon.clear_chrome_process, self.port, timeout,
            max_deaths)

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
        asyncio.ensure_future(self.close())
