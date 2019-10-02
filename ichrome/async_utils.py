# fast and stable connection
import asyncio
import json
import time
import traceback
from asyncio.futures import Future, TimeoutError

from pyee import AsyncIOEventEmitter
from torequests.dummy import Requests
from torequests.utils import quote_plus, urljoin, UA

from .logs import ichrome_logger as logger
"""
Async utils for connections and operations.
[Recommended] Use daemon and async utils with different scripts.
"""

# 必要时候用 once 只要有任务就清掉? 或者不需要绑定时候, 等待的时候清理 https://pyee.readthedocs.io/en/latest/
# async for message in websocket: https://websockets.readthedocs.io/en/stable/intro.html#synchronization-example

# ee = AsyncIOEventEmitter()

# @ee.on('event')
# async def event_handler(abc):
#     print(abc)
#     print('BANG BANG')
# ee.emit('event', abc=123342)


class EventFuture(Future):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def wait_result(self, timeout=None):
        try:
            result = await asyncio.wait_for(self, timeout=timeout)
        except TimeoutError as e:
            result = e
        return result


# f = EventFuture()

# async def fill():
#     await asyncio.sleep(3.3)
#     f.set_result('ok')

# asyncio.ensure_future(fill())

# async def test():
#     result = await f.wait_result(1)
#     print(result)
#     print(isinstance(result, TimeoutError))

# asyncio.get_event_loop().run_until_complete(test())


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
                Tab.create_tab(rjson, chrome=self)
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
        self.ee = AsyncIOEventEmitter(loop=self.loop)
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
            return True
        else:
            self.status = 'disconnected'
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
            tab = Tab.create_tab(rjson, chrome=self)
            tab._created_time = tab.now
            logger.info(f"new tab {tab}")
            return tab

    async def do_tab(self, tab_id, action):
        ok = False
        if isinstance(tab_id, self.__class__):
            tab_id = tab_id.tab_id
        r = await self.get_server(f"/json/{action}/{tab_id}")
        if r:
            if action == 'close':
                ok = r.text == "Target is closing"
            elif action == 'activate':
                ok = r.text == "Target activated"
            else:
                ok == r.text
        logger.info(f"{action} tab {tab_id}: {ok}")
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
        return f"<Chrome: {self.port}({self.status})>"

    def __str__(self):
        return f"<Chrome: {self.server}({self.status})>"


class Tab(object):

    def __init__(self,
                 tab_id,
                 title=None,
                 url=None,
                 webSocketDebuggerUrl=None,
                 json=None,
                 chrome=None,
                 timeout=5,
                 loop=None):
        self.tab_id = tab_id
        self.title = title
        self._url = url
        self.webSocketDebuggerUrl = webSocketDebuggerUrl
        self.json = json
        self.chrome = chrome
        self.timeout = timeout
        self.loop = loop
        self._created_time = None
        # self.lock = asyncio.Lock()
        # async with lock:

        # self.req = tPool()
        # self._message_id = 0
        # self._listener = Listener()
        # self.lock = threading.Lock()
        # self.ws = websocket.WebSocket()
        # self._connect()
        # for target in [self._recv_daemon]:
        #     t = threading.Thread(target=target, daemon=True)
        #     t.start()

    @classmethod
    def create_tab(cls, tab_json, chrome=None):
        if isinstance(tab_json, str):
            tab_json = json.loads(tab_json)
        elif not isinstance(tab_json, dict):
            raise ValueError('tab_json type should be dict / json string')
        return cls(
            tab_id=tab_json["id"],
            title=tab_json["title"],
            url=tab_json["url"],
            webSocketDebuggerUrl=tab_json["webSocketDebuggerUrl"],
            json=tab_json,
            chrome=chrome,
            loop=chrome.loop if chrome else None)

    @property
    def url(self):
        return self._url

    async def refresh(self):
        for tab in await self.chrome.tabs:
            if tab.tab_id == self.tab_id:
                self.tab_id = tab.tab_id
                self.title = tab.title
                self._url = tab.url
                self.webSocketDebuggerUrl = tab.webSocketDebuggerUrl
                self.json = tab.json
                return True
        return False

    def _connect(self):
        self.ws.connect(self.webSocketDebuggerUrl, timeout=self.timeout)

    async def activate_tab(self):
        """activate tab with chrome http endpoint"""
        return await self.chrome.activate_tab(self.tab_id)

    async def close_tab(self):
        """close tab with chrome http endpoint"""
        return await self.chrome.close_tab(self.tab_id)

    async def activate(self):
        """activate tab with cdp websocket"""
        return await self.send("Page.bringToFront")

    async def close(self):
        """close tab with cdp websocket"""
        return await self.send("Page.setTouchEmulationEnabled")

    async def crash(self):
        return await self.send("Page.crash")

    def _recv_daemon(self):
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
        while self.ws.connected:
            try:
                data_str = self.ws.recv()
                logger.debug(data_str)
                if not data_str:
                    continue
                try:
                    data_dict = json.loads(data_str)
                    if not isinstance(data_dict, dict):
                        continue
                except (TypeError, json.decoder.JSONDecodeError):
                    continue
                f = self._listener.find_future(data_dict)
                if f:
                    f.set_result(data_str)
            except (
                    websocket._exceptions.WebSocketConnectionClosedException,
                    ConnectionResetError,
            ):
                break

    def send(self,
             method,
             timeout=None,
             callback=None,
             mute_log=False,
             **kwargs):
        try:
            timeout = self.timeout if timeout is None else timeout
            request = {"method": method, "params": kwargs}
            self._message_id += 1
            request["id"] = self._message_id
            if not mute_log:
                logger.info("<%s> send: %s" % (self, request))
            with self.lock:
                self.ws.send(json.dumps(request))
            res = self.recv({
                "id": request["id"]
            },
                            timeout=timeout,
                            callback=callback)
            return res
        except (
                websocket._exceptions.WebSocketTimeoutException,
                websocket._exceptions.WebSocketConnectionClosedException,
        ):
            self.refresh_ws()

    def recv(self, arg, timeout=None, callback=None):
        """arg type: dict"""
        result = None
        timeout = self.timeout if timeout is None else timeout
        if timeout == 0:
            return result
        f = self._listener.register(arg, timeout=timeout)
        try:
            result = f.x
        except Error:
            result = None
        finally:
            self._listener.find_future(arg)
            return callback(result) if callable(callback) else result

    def refresh_ws(self):
        self.ws.close()
        self._connect()

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
            event="",
            timeout=None,
            callback=None,
            filter_function=None,
            wait_seconds=None,
    ):
        timeout = self.timeout if timeout is None else timeout
        start_time = time.time()
        while 1:
            result = self.recv({
                "method": event
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

    def js(self, javascript, mute_log=False):
        """
        Evaluate JavaScript on the page
        """
        return self.send(
            "Runtime.evaluate", expression=javascript, mute_log=mute_log)

    def querySelectorAll(self, cssselector, index=None, action=None):
        """
        tab.querySelectorAll("#sc_hdu>li>a", index=2, action="removeAttribute('href')")
        for i in tab.querySelectorAll("#sc_hdu>li"):
        ichrome_logger.info(
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
            response = self.js(javascript, mute_log=True)
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
            logger.info(
                "querySelectorAll error: %s, response: %s" % (e, response))
            if isinstance(index, int):
                return None
            return []

    async def inject_js(self,
                        url,
                        timeout=None,
                        retry=0,
                        verify=0,
                        **requests_kwargs):
        # js_source_code = """
        # var script=document.createElement("script");
        # script.type="text/javascript";
        # script.src="{}";
        # document.getElementsByTagName('head')[0].appendChild(script);
        # """.format(url)
        if self.chrome:
            req = self.chrome.req
        else:
            req = Requests(loop=self.loop)
        r = await req.get(
            url, timeout=timeout, retry=retry, headers={'User-Agent': UA.Chrome}, verify=verify, **requests_kwargs)
        if r:
            javascript = r.text
            return self.js(javascript, mute_log=True)
        else:
            logger.info("inject_js failed for request: %s" % r.text)
            return

    def click(self, cssselector, index=0, action="click()"):
        """
        tab.click("#sc_hdu>li>a") # click first node's link.
        tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
        """
        return self.querySelectorAll(cssselector, index=index, action=action)

    def __str__(self):
        return f"ChromeTab({self.tab_id}, {self.title}, {self.url}, {self.chrome})"

    def __repr__(self):
        return f'ChromeTab({self.url})'

    # def __del__(self):
    #     with self.lock:
    #         self.ws.close()


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

    def __init__(self, timeout=None):
        self.timeout = timeout
        self.container = []
        self.id_futures = WeakValueDictionary()
        self.method_futures = WeakValueDictionary()
        self.other_futures = WeakValueDictionary()

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

    def register(self, arg, timeout=None):
        """
        arg type: dict.
        """
        if not isinstance(arg, dict):
            raise TypeError(
                "Listener should register a dict arg, such as {'id': 1} or {'method': 'Page.loadEventFired'}"
            )
        f = NewFuture(timeout=timeout)
        if "id" in arg:
            # id is unique
            self.id_futures[arg["id"]] = f
        elif "method" in arg:
            # method may be duplicate
            self.method_futures[arg["method"]] = f
        else:
            self.other_futures[self._normalize_dict(arg)] = f
        return f

    def find_future(self, arg):
        if "id" in arg:
            # id is unique
            f = self.id_futures.pop(arg["id"], None)
        elif "method" in arg:
            # method may be duplicate
            f = self.method_futures.pop(arg["method"], None)
        else:
            f = self.other_futures.pop(self._normalize_dict(arg), None)
        return f
