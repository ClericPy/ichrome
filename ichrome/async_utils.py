# fast and stable connection
import asyncio
import json
import time
import inspect
import traceback
from asyncio.futures import Future, TimeoutError
from weakref import WeakValueDictionary

from aiohttp.client_exceptions import ClientError
from aiohttp.http import WebSocketError, WSMsgType
from torequests.dummy import Requests
from torequests.utils import UA, quote_plus, urljoin

from .logs import logger
"""
Async utils for connections and operations.
[Recommended] Use daemon and async utils with different scripts.
"""


class Chrome:

    def __init__(self,
                 host="127.0.0.1",
                 port=9222,
                 timeout=2,
                 retry=1,
                 loop=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry = retry
        self.loop = loop
        self.status = 'init'
        self.req = None

    @property
    def server(self):
        """return like 'http://127.0.0.1:9222'"""
        return "http://%s:%d" % (self.host, self.port)

    async def get_server(self, api=''):
        # maybe return fail request
        url = urljoin(self.server, api)
        resp = await self.req.get(url, timeout=self.timeout, retry=self.retry)
        if not resp:
            self.status = resp.text
        return resp

    async def get_tabs(self, filt_page_type=True):
        """`await self.get_tabs()`
        /json"""
        try:
            r = await self.get_server('/json')
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
    def tabs(self):
        """`await self.tabs`"""
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        return self.get_tabs()

    async def get_version(self):
        """`await self.get_version()`
        /json/version"""
        r = await self.get_server('/json/version')
        if r:
            return r.json()
        else:
            raise r.error

    @property
    def version(self):
        """`await self.version`
        {'Browser': 'Chrome/77.0.3865.90', 'Protocol-Version': '1.3', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'V8-Version': '7.7.299.11', 'WebKit-Version': '537.36 (@58c425ba843df2918d9d4b409331972646c393dd)', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/b5fbd149-959b-4603-b209-cfd26d66bdc1'}"""
        return self.get_version()

    async def connect(self):
        """await self.connect()"""
        self.req = Requests(loop=self.loop)
        if await self.check():
            return self
        else:
            return None

    async def check(self):
        """Test http connection to cdp. `await self.check()`
        """
        r = await self.get_server()
        if r:
            self.status = 'connected'
            logger.debug(f'[{self.status}] {self}.')
            return True
        else:
            self.status = 'disconnected'
            logger.debug(f'[{self.status}] {self}.')
            return False

    @property
    def ok(self):
        """await self.ok"""
        return self.check()

    async def new_tab(self, url=""):
        api = f'/json/new?{quote_plus(url)}'
        r = await self.get_server(api)
        if r:
            rjson = r.json()
            tab = Tab(chrome=self, **rjson)
            tab._created_time = tab.now
            logger.debug(f"[new_tab] {tab} {rjson}")
            return tab

    async def do_tab(self, tab_id, action):
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

    async def activate_tab(self, tab_id):
        return await self.do_tab(tab_id, action='activate')

    async def close_tab(self, tab_id):
        return await self.do_tab(tab_id, action='close')

    async def close_tabs(self, tab_ids=None):
        if tab_ids is None:
            tab_ids = await self.tabs
        return [await self.close_tab(tab_id) for tab_id in tab_ids]

    def __repr__(self):
        return f"<Chrome({self.status}): {self.port}>"

    def __str__(self):
        return f"<Chrome({self.status}): {self.server}>"



class EventFuture(Future):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # def __del__(self):
    #     logger.debug('future deleted')


class WSConnection(object):

    def __init__(self, tab):
        self.tab = tab
        self._closed = None

    async def __aenter__(self):
        self.tab.ws = await self.tab.session.ws_connect(
            self.tab.webSocketDebuggerUrl,
            timeout=self.tab.timeout,
            **self.tab.ws_kwargs)
        asyncio.ensure_future(self.tab._recv_daemon(), loop=self.tab.loop)
        logger.debug(f'[connected] {self.tab} websocket connection created.')
        return self.tab.ws

    async def __aexit__(
            self,
            exc_type,
            exc_value,
            traceback,
    ):
        await self.tab.ws.close()
        self._closed = self.tab.ws.closed
        self.tab.ws = None

    def __del__(self):
        logger.debug(
            f'[disconnected] {self.tab!r} ws connection closed={self._closed}')


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
    def status(self):
        status = 'disconnected'
        if self.ws and not self.ws.closed:
            status = 'connected'
        return status

    @property
    def connect(self):
        '''async with tab.connect:'''
        return WSConnection(self)

    def __call__(self):
        '''async with tab():'''
        return WSConnection(self)

    @property
    def msg_id(self):
        self._message_id += 1
        return self._message_id

    @property
    def url(self):
        """The init url while tab created.
        await self.current_url for the current url.
        """
        return self._url

    async def refresh_tab_info(self):
        for tab in await self.chrome.tabs:
            if tab.tab_id == self.tab_id:
                self.tab_id = tab.tab_id
                self.title = tab.title
                self._url = tab.url
                self.webSocketDebuggerUrl = tab.webSocketDebuggerUrl
                self.json = tab.json
                return True
        return False

    async def activate_tab(self):
        """activate tab with chrome http endpoint"""
        return await self.chrome.activate_tab(self)

    async def close_tab(self):
        """close tab with chrome http endpoint"""
        return await self.chrome.close_tab(self)

    async def activate(self):
        """activate tab with cdp websocket"""
        return await self.send("Page.bringToFront")

    async def close(self):
        """close tab with cdp websocket"""
        return await self.send("Page.close")

    async def crash(self):
        return await self.send("Page.crash")

    async def _recv_daemon(self):
        """
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
                continue
            f = self._listener.find_future(data_dict)
            if f:
                f.set_result(data_str)
        logger.debug(f'[break] {self!r} _recv_daemon loop break.')

    async def send(self, method: str, timeout=None, callback=None, **kwargs):
        request = {"method": method, "params": kwargs}
        msg_id = self.msg_id
        request["id"] = msg_id
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
            event = {"id": msg_id}
            msg = await self.recv(event, timeout=timeout, callback=callback)
            return msg
        except (ClientError, WebSocketError) as err:
            logger.error(f'{self} [send] msg failed for {err}')
            return None

    async def recv(self, event_dict: dict, timeout=None, callback=None) -> dict:
        """Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.

        :param event_dict: dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
        :type event_dict: dict
        :param timeout: await seconds, None for permanent, 0 for 0 seconds.
        :type timeout: float / None, optional
        :param callback: event callback function with only one arg(the event json).
        :type callback: callable, optional
        :return: the event dict from websocket recv.
        :rtype: dict
        """
        result: dict = {}
        timeout = self.timeout if timeout is None else timeout
        if timeout <= 0:
            return result
        f = self._listener.register(event_dict)
        try:
            result = await asyncio.wait_for(f, timeout=timeout)
        except TimeoutError:
            logger.debug(f'{event_dict} wait recv timeout.')
        finally:
            self._listener.find_future(event_dict)
            if callable(callback):
                callback_result = callback(result)
            else:
                return result
            if inspect.isawaitable(callback_result):
                return await callback_result
            else:
                return callback_result

    @property
    def now(self):
        return int(time.time())

    def clear_cookies(self, timeout=0):
        return self.send("Network.clearBrowserCookies", timeout=timeout)

    def delete_cookies(self, name, url=None, domain=None, path=None, timeout=0):
        return self.send(
            "Network.deleteCookies",
            name=name,
            url=None,
            domain=None,
            path=None,
            timeout=None,
        )

    def get_cookies(self, urls=None, timeout=None):
        if urls:
            if isinstance(urls, str):
                urls = [urls]
            urls = list(urls)
            result = self.send("Network.getCookies", urls=urls, timeout=None)
        else:
            result = self.send("Network.getCookies", timeout=None)
        try:
            return json.loads(result)["result"]["cookies"]
        except Exception:
            return []

    @property
    def current_url(self):
        return json.loads(
            self.js("window.location.href"))["result"]["result"]["value"]

    @property
    def html(self):
        """return"""
        response = None
        try:
            response = self.js("document.documentElement.outerHTML")
            if not response:
                return ""
            result = json.loads(response)
            value = result["result"]["result"]["value"]
            return value
        except (KeyError, json.decoder.JSONDecodeError):
            logger.error("tab.content error %s:\n%s" % (response,
                                                        traceback.format_exc()))
            return ""

    def wait_loading(self, timeout=None, callback=None):
        data = self.wait_event(
            "Page.loadEventFired", timeout=timeout, callback=callback)
        return data

    def wait_event(
            self,
            event_name="",
            timeout=None,
            callback=None,
            filter_function=None,
            wait_seconds=None,
    ):
        timeout = self.timeout if timeout is None else timeout
        start_time = time.time()
        while 1:
            result = self.recv({
                "method": event_name
            },
                               timeout=timeout,
                               callback=callback)
            if not callable(filter_function) or filter_function(result):
                break
            if wait_seconds and time.time() - start_time > wait_seconds:
                break
        return result

    def reload(self, timeout=5):
        """
        Reload the page
        """
        return self.set_url(timeout=timeout)

    def set_url(self, url=None, referrer=None, timeout=5):
        """
        Navigate the tab to the URL
        """
        self.send("Page.enable", timeout=0)
        start_load_ts = self.now
        if url:
            self._url = url
            if referrer is None:
                data = self.send("Page.navigate", url=url, timeout=timeout)
            else:
                data = self.send(
                    "Page.navigate",
                    url=url,
                    referrer=referrer,
                    timeout=timeout)
        else:
            data = self.send("Page.reload", timeout=timeout)
        time_passed = self.now - start_load_ts
        real_timeout = max((timeout - time_passed, 0))
        if self.wait_loading(timeout=real_timeout) is None:
            self.send("Page.stopLoading", timeout=0)
        return data

    def js(self, javascript):
        """
        Evaluate JavaScript on the page
        """
        logger.debug(f'{self!r} insert js {javascript[:100]} ...')
        return self.send("Runtime.evaluate", expression=javascript)

    def querySelectorAll(self, cssselector, index=None, action=None):
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
            response = self.js(javascript, log=False)
            response = json.loads(response)["result"]["result"]["value"]
            items = json.loads(response)
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
            logger.error('WSConnection is not closed')
            asyncio.ensure_future(self.ws.close())


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
        f = EventFuture()
        key = self._arg_to_key(event_dict)
        self._registered_futures[key] = f
        return f

    def find_future(self, event_dict):
        key = self._arg_to_key(event_dict)
        return self._registered_futures.get(key)
