# fast and stable connection
import asyncio
import inspect
import json
import time
import traceback
from asyncio.futures import Future, TimeoutError
from typing import Any, Callable, Coroutine, List, Optional, Union
from weakref import WeakValueDictionary

from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.dummy import NewResponse, Requests
from torequests.utils import UA, quote_plus, urljoin

from .logs import logger
"""
Async utils for connections and operations.
[Recommended] Use daemon and async utils with different scripts.
"""


class InvalidRequests(object):

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            'Chrome has not connected. `await chrome.connect()` before request.'
        )


class Chrome:

    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 9222,
                 timeout: int = 2,
                 retry: int = 1,
                 loop: Any = None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry = retry
        self.loop = loop
        self.status = 'init'
        self.req = InvalidRequests()

    @property
    def server(self) -> str:
        """return like 'http://127.0.0.1:9222'"""
        return "http://%s:%d" % (self.host, self.port)

    async def get_server(self, api: str = '') -> 'NewResponse':
        # maybe return failure request
        url = urljoin(self.server, api)
        resp = await self.req.get(url, timeout=self.timeout, retry=self.retry)
        if not resp:
            self.status = resp.text
        return resp

    async def get_tabs(self, filt_page_type: bool = True) -> List['Tab']:
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

    @property
    def tabs(self) -> Coroutine[Any, Any, List['Tab']]:
        """`await self.tabs`"""
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        return self.get_tabs()

    async def get_version(self) -> dict:
        """`await self.get_version()`
        /json/version"""
        r = await self.get_server('/json/version')
        if r:
            return r.json()
        else:
            raise r.error

    @property
    def version(self) -> Coroutine[Any, Any, dict]:
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
            logger.debug(f'[{self.status}] checked by {self}.')
            return True
        else:
            self.status = 'disconnected'
            logger.debug(f'[{self.status}] checked by {self}.')
            return False

    @property
    def ok(self):
        """await self.ok"""
        return self.check()

    async def new_tab(self, url: str = "") -> Union['Tab', None]:
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

    async def do_tab(self, tab_id: Union['Tab', str],
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

    async def activate_tab(self, tab_id: Union['Tab', str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='activate')

    async def close_tab(self, tab_id: Union['Tab', str]) -> Union[str, bool]:
        return await self.do_tab(tab_id, action='close')

    async def close_tabs(self,
                         tab_ids: Union[None, List['Tab'], List[str]] = None,
                         *args) -> List[Union[str, bool]]:
        if tab_ids is None:
            tab_ids = await self.tabs
        return [await self.close_tab(tab_id) for tab_id in tab_ids]

    def connect_tabs(self,
                     tabs: Union[List['Tab'], 'Tab']) -> 'TabConnectionManager':
        '''async with chrome.connect_tabs([tab1, tab2]):.
        or
        async with chrome.connect_tabs(tab1)'''
        if not (isinstance(tabs, (list, set))):
            tabs = [tabs]
        return TabConnectionManager(tabs)

    def __repr__(self):
        return f"<Chrome({self.status}): {self.port}>"

    def __str__(self):
        return f"<Chrome({self.status}): {self.server}>"


class TabConnectionManager(object):

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


class WSConnection(object):

    def __init__(self, tab):
        self.tab = tab
        self._closed = None

    def __str__(self):
        return f'<{self.__class__.__name__}: {not self._closed}>'

    async def __aenter__(self):
        return await self.connect()

    async def connect(self):
        """Connect to ws, and set tab.ws as aiohttp.client_ws.ClientWebSocketResponse."""
        self.tab.ws = await self.tab.session.ws_connect(
            self.tab.webSocketDebuggerUrl,
            timeout=self.tab.timeout,
            **self.tab.ws_kwargs)
        # start the daemon background.
        asyncio.ensure_future(self.tab._recv_daemon(), loop=self.tab.loop)
        logger.debug(f'[connected] {self.tab} websocket connection created.')
        return self.tab.ws

    async def shutdown(self):
        if not self._closed:
            await self.tab.ws.close()
            self._closed = self.tab.ws.closed
            self.tab.ws = None

    async def __aexit__(self, *args):
        await self.shutdown()

    def __del__(self):
        logger.debug(
            f'[disconnected] {self.tab!r} ws_connection closed[{self._closed}]')


class Tab(object):

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
        self.session = self.req.session
        self._listener = Listener()

    @property
    def status(self) -> str:
        status = 'disconnected'
        if self.ws and not self.ws.closed:
            status = 'connected'
        return status

    @property
    def connect(self) -> WSConnection:
        '''`async with tab.connect:`'''
        return WSConnection(self)

    def __call__(self) -> WSConnection:
        '''`async with tab():`'''
        return WSConnection(self)

    @property
    def msg_id(self):
        self._message_id += 1
        return self._message_id

    @property
    def url(self) -> str:
        """The init url while tab created.
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
                f.set_result(data_dict)
        logger.debug(f'[break] {self!r} _recv_daemon loop break.')

    async def send(self,
                   method: str,
                   timeout: Union[int, float] = None,
                   callback: Optional[Callable] = None,
                   **kwargs) -> Union[None, dict]:
        request = {"method": method, "params": kwargs}
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
            msg = await self.recv(event, timeout=timeout, callback=callback)
            return msg
        except (ClientError, WebSocketError) as err:
            logger.error(f'{self} [send] msg failed for {err}')
            return None

    async def recv(self,
                   event_dict: dict,
                   timeout: Union[int, float] = None,
                   callback=None) -> Union[dict, None]:
        """Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.

        :param event_dict: dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
        :type event_dict: dict
        :param timeout: await seconds, None for permanent, 0 for 0 seconds.
        :type timeout: float / None, optional
        :param callback: event callback function accept only one arg(the event dict).
        :type callback: callable, optional
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
            logger.debug(f'[timeout] {event_dict} recv timeout.')
        finally:
            if callable(callback):
                callback_result = callback(result)
            else:
                return result
            if inspect.isawaitable(callback_result):
                return await callback_result
            else:
                return callback_result

    @property
    def now(self) -> int:
        return int(time.time())

    async def clear_cookies(self, timeout: Union[int, float] = 0):
        """clearBrowserCookies"""
        return await self.send("Network.clearBrowserCookies", timeout=timeout)

    async def delete_cookies(self,
                             name,
                             url=None,
                             domain=None,
                             path=None,
                             timeout: Union[int, float] = 0):
        """deleteCookies by name, with url / domain / path."""
        return await self.send(
            "Network.deleteCookies",
            name=name,
            url=None,
            domain=None,
            path=None,
            timeout=None,
        )

    async def get_cookies(self,
                          urls: Union[List[str], str] = None,
                          timeout: Union[int, float] = None) -> List:
        """get cookies of urls."""
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

    async def get_current_url(self):
        result = await self.js("window.location.href")
        url = json.loads(result)["result"]["result"]["value"]
        return url

    @property
    def current_url(self) -> str:
        return self.get_current_url()

    async def get_html(self) -> str:
        """return html from `document.documentElement.outerHTML`"""
        response = None
        try:
            response = await self.js("document.documentElement.outerHTML")
            if not response:
                return ""
            value = response["result"]["result"]["value"]
            return value
        except (KeyError, json.decoder.JSONDecodeError):
            logger.error("tab.content error %s:\n%s" % (response,
                                                        traceback.format_exc()))
            return ""

    @property
    def html(self) -> Coroutine[Any, Any, str]:
        """`await tab.html`. return html from `document.documentElement.outerHTML`"""
        return self.get_html()

    async def wait_loading(
            self,
            timeout: Union[int, float] = None,
            callback: Optional[Callable] = None) -> Union[dict, None]:
        data = await self.wait_event(
            "Page.loadEventFired", timeout=timeout, callback=callback)
        return data

    async def wait_event(
            self,
            event_name: str,
            timeout: Union[int, float] = None,
            callback: Optional[Callable] = None,
            filter_function: Optional[Callable] = None,
            max_wait_seconds: Union[int, float] = None,
    ) -> Union[dict, None]:
        """Similar to self.recv, but has the filter_function to distinct duplicated method of event."""
        timeout = self.timeout if timeout is None else timeout
        start_time = time.time()
        while 1:
            # avoid same method but different event occured, use filter_function
            event = {"method": event_name}
            result = await self.recv(event, timeout=timeout, callback=callback)
            if not (filter_function and filter_function(result)):
                break
            if max_wait_seconds and time.time() - start_time > max_wait_seconds:
                break
        return result

    async def reload(self, timeout: Union[None, float, int] = 5):
        """
        Reload the page
        """
        return await self.set_url(timeout=timeout)

    async def set_url(self,
                      url: Optional[str] = None,
                      referrer: Optional[str] = None,
                      timeout: Union[None, float, int] = None):
        """
        Navigate the tab to the URL
        """
        if timeout is None:
            timeout = 5
        logger.debug(f'[set_url] {self!r} url => {url}')
        await self.send("Page.enable", timeout=0)
        start_load_ts = self.now
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
        if (await self.wait_loading(timeout=real_timeout)) is None:
            await self.send("Page.stopLoading", timeout=0)
        return data

    async def js(self, javascript: str) -> Union[None, dict]:
        """
        Evaluate JavaScript on the page
        """
        logger.debug(f'[js] {self!r} insert js `{javascript}`.')
        return await self.send("Runtime.evaluate", expression=javascript)

    async def querySelectorAll(self,
                               cssselector: str,
                               index: Union[None, int, str] = None,
                               action: Union[None, str] = None):
        """
        tab.querySelectorAll("#sc_hdu>li>a", index=2, action="removeAttribute('href')")
        for i in tab.querySelectorAll("#sc_hdu>li"):
        logger.info(
                "Tag: %s, id:%s, class:%s, text:%s"
                % (i, i.get("id"), i.get("class"), i.text)
            )
        """
        if "'" in cssselector:
            cssselector = cssselector.replace("'", "\\'")
        if index is None:
            index = "null"
        else:
            index = int(index)
        if action:
            action = (
                "item.result=el.%s || '';item.result=item.result.toString()" %
                action)
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
            response = (await self.js(javascript)) or {}
            response_items_str = response["result"]["result"]["value"]
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
            logger.error(
                "querySelectorAll error: %s, response: %s" % (e, response))
            if isinstance(index, int):
                return None
            return []

    async def inject_js_url(self,
                            url,
                            timeout=None,
                            retry=0,
                            verify=0,
                            **requests_kwargs):

        r = await self.req.get(
            url,
            timeout=timeout,
            retry=retry,
            headers={'User-Agent': UA.Chrome},
            verify=verify,
            **requests_kwargs)
        if r:
            javascript = r.text
            return self.js(javascript, log=False)
        else:
            logger.error("inject_js_url failed for request: %s" % r.text)
            return

    def click(self, cssselector, index=0, action="click()"):
        """
        tab.click("#sc_hdu>li>a") # click first node's link.
        tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
        """
        return self.querySelectorAll(cssselector, index=index, action=action)

    def __str__(self):
        return f"<Tab({self.status}{self.chrome!r}): {self.tab_id}>"

    def __repr__(self):
        return f"<Tab({self.status}): {self.tab_id}>"

    def __del__(self):
        if self.ws:
            logger.debug('[unclosed] WSConnection is not closed.')
            asyncio.ensure_future(self.ws.close(), loop=self.loop)


class Tag(object):

    def __init__(self, tagName, innerHTML, outerHTML, textContent, attributes,
                 result):
        self.tagName = tagName.lower()
        self.innerHTML = innerHTML
        self.outerHTML = outerHTML
        self.textContent = textContent
        self.attributes = attributes
        self.result = result

        self.text = textContent

    def get(self, name, default=None):
        return self.attributes.get(name, default)

    def to_dict(self):
        return {
            "tagName": self.tagName,
            "innerHTML": self.innerHTML,
            "outerHTML": self.outerHTML,
            "textContent": self.textContent,
            "attributes": self.attributes,
            "result": self.result,
        }

    def __str__(self):
        return "Tag(%s)" % self.tagName

    def __repr__(self):
        return self.__str__()


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
