import json
import threading
import time
import traceback
from concurrent.futures._base import Error
from weakref import WeakValueDictionary

import websocket
from torequests import NewFuture, tPool
from torequests.utils import quote_plus

from .logs import logger
"""
Sync utils for connections and operations.
"""


class Chrome(object):

    def __init__(self, host="127.0.0.1", port=9222, timeout=2, retry=1):
        self.req = tPool()
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry = retry
        if not self.ok:
            raise IOError("Can not connect to %s" % self.server)

    @property
    def ok(self):
        """
        Test connection to browser
        """
        r = self.req.get(self.server, timeout=self.timeout, retry=self.retry)
        if r.ok:
            return True
        return False

    def _get_tabs(self):
        """
        Get all open browser tabs that are pages tabs
        """
        try:
            r = self.req.get(
                self.server + "/json", timeout=self.timeout, retry=self.retry)
            return [
                Tab(
                    tab["id"],
                    tab["title"],
                    tab["url"],
                    tab["webSocketDebuggerUrl"],
                    self,
                ) for tab in r.json() if tab["type"] == "page"
            ]
        except Exception:
            traceback.print_exc()
            return []

    @property
    def server(self):
        return "http://%s:%d" % (self.host, self.port)

    @property
    def tabs(self):
        return self._get_tabs()

    def new_tab(self, url=""):
        r = self.req.get(
            "%s/json/new?%s" % (self.server, quote_plus(url)),
            retry=self.retry,
            timeout=self.timeout,
        )
        if r.x and r.ok:
            rjson = r.json()
            tab_id, title, _url, webSocketDebuggerUrl = (
                rjson["id"],
                rjson["title"],
                rjson["url"],
                rjson["webSocketDebuggerUrl"],
            )
            tab = Tab(tab_id, title, _url, webSocketDebuggerUrl, self)
            tab._create_time = tab.now
            logger.info("new tab %s" % (tab))
            return tab

    def activate_tab(self, tab_id):
        ok = False
        if isinstance(tab_id, Tab):
            tab_id = tab_id.tab_id
        r = self.req.get(
            "%s/json/activate/%s" % (self.server, tab_id),
            retry=self.retry,
            timeout=self.timeout,
        )
        if r.x and r.ok:
            if r.text == "Target activated":
                ok = True
        logger.info("activate_tab %s: %s" % (tab_id, ok))

    def close_tab(self, tab_id=None):
        ok = False
        tab_id = tab_id or self.tabs
        if isinstance(tab_id, Tab):
            tab_id = tab_id.tab_id
        r = self.req.get(
            "%s/json/close/%s" % (self.server, tab_id),
            retry=self.retry,
            timeout=self.timeout,
        )
        if r.x and r.ok:
            if r.text == "Target is closing":
                ok = True
        logger.info("close tab %s: %s" % (tab_id, ok))

    def close_tabs(self, tab_ids):
        return [self.close_tab(tab_id) for tab_id in tab_ids]

    @property
    def meta(self):
        r = self.req.get(
            "%s/json/version" % self.server,
            retry=self.retry,
            timeout=self.timeout)
        if r.x and r.ok:
            return r.json()

    def __str__(self):
        return "[Chromote(tabs=%d)]" % len(self.tabs)

    def __repr__(self):
        return "Chromote(%s)" % (self.server)

    def __getitem__(self, index):
        tabs = self.tabs
        if isinstance(index, int):
            if len(tabs) > index:
                return tabs[index]
        elif isinstance(index, slice):
            return tabs.__getitem__(index)


class Tab(object):

    def __init__(self,
                 tab_id,
                 title,
                 url,
                 webSocketDebuggerUrl,
                 chrome,
                 timeout=5):
        self.tab_id = tab_id
        self.title = title
        self._url = url
        self.webSocketDebuggerUrl = webSocketDebuggerUrl
        self.chrome = chrome
        self.timeout = timeout

        self.req = tPool()
        self._create_time = time.time()
        self._message_id = 0
        self._listener = Listener()
        self.lock = threading.Lock()
        self.ws = websocket.WebSocket()
        self._connect()
        for target in [self._recv_daemon]:
            t = threading.Thread(target=target, daemon=True)
            t.start()

    @property
    def url(self):
        return self._url

    def _connect(self):
        self.ws.connect(self.webSocketDebuggerUrl, timeout=self.timeout)

    def activate_tab(self):
        return self.chrome.activate_tab(self.tab_id)

    def close_tab(self):
        return self.chrome.close_tab(self.tab_id)

    def activate(self):
        return self.send("Page.bringToFront")

    def close(self):
        return self.send("Page.close")

    def crash(self):
        return self.send("Page.crash")

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
            request = {"id": request["id"]}
            res = self.recv(request, timeout=timeout, callback=callback)
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
            url=url,
            domain=domain,
            path=path,
            timeout=timeout,
        )

    def get_cookies(self, urls=None, timeout=None):
        if urls:
            if isinstance(urls, str):
                urls = [urls]
            urls = list(urls)
            result = self.send("Network.getCookies", urls=urls, timeout=timeout)
        else:
            result = self.send("Network.getCookies", timeout=timeout)
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
            request = {"method": event}
            result = self.recv(request, timeout=timeout, callback=callback)
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

    def inject_js_url(self,
                      url,
                      timeout=None,
                      retry=0,
                      verify=0,
                      **requests_kwargs):
        return self.inject_js(
            url, timeout=timeout, retry=retry, verify=verify, **requests_kwargs)

    def inject_js(self, url, timeout=None, retry=0, verify=0,
                  **requests_kwargs):
        # js_source_code = """
        # var script=document.createElement("script");
        # script.type="text/javascript";
        # script.src="{}";
        # document.getElementsByTagName('head')[0].appendChild(script);
        # """.format(url)
        r = self.req.get(
            url, timeout=timeout, retry=retry, verify=verify, **requests_kwargs)
        if r.x and r.ok:
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
        return "Tab(%s)" % (self.url)

    def __repr__(self):
        return 'ChromeTab("%s", "%s", "%s", port: %s)' % (
            self.tab_id,
            self.title,
            self.url,
            self.chrome.port,
        )

    def __del__(self):
        with self.lock:
            self.ws.close()


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


def main():
    pass


if __name__ == "__main__":
    main()
