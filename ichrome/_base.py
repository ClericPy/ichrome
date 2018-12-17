import json
import os
import socket
import subprocess
import threading
import time
import traceback
from concurrent.futures._base import Error
from weakref import WeakValueDictionary

import psutil
import websocket
from torequests import NewFuture, tPool
from torequests.utils import quote_plus, timepass, ttime
from torequests.versions import IS_WINDOWS

from ._logs import ichrome_logger as logger


class ChromeDaemon(object):
    """create chrome process.
    max_deaths: max_deaths=2 means should quick shutdown chrome twice to skip auto_restart.

    default extra_config: ["--disable-gpu", "--no-sandbox", "--no-first-run"]

    common args:
    --incognito: Causes the browser to launch directly in incognito mode
    --mute-audio: Mutes audio sent to the audio device so it is not audible during automated testing.
    --blink-settings=imagesEnabled=false: disable image loading.

    --disable-javascript
    --disable-extensions
    --disable-background-networking
    --safebrowsing-disable-auto-update
    --disable-sync
    --ignore-certificate-errors
    –disk-cache-dir=xxx: Use a specific disk cache location, rather than one derived from the UserDatadir.
    --disk-cache-size: Forces the maximum disk space to be used by the disk cache, in bytes.
    --single-process
    --proxy-pac-url=xxx

    see more args: https://peter.sh/experiments/chromium-command-line-switches/
    """

    port_in_using = set()
    PC_UA = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36"
    MAC_OS_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0_1) Version/8.0.1a Safari/728.28.19"
    )
    WECHAT_UA = "Mozilla/5.0 (Linux; Android 5.0; SM-N9100 Build/LRX21V) > AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 > Chrome/37.0.0.0 Mobile Safari/537.36 > MicroMessenger/6.0.2.56_r958800.520 NetType/WIFI"
    IPAD_UA = "Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1"
    MOBILE_UA = "Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Mobile Safari/537.36"

    def __init__(
        self,
        chrome_path=None,
        host="localhost",
        port=9222,
        headless=False,
        user_agent=None,
        proxy=None,
        user_data_dir=None,
        disable_image=False,
        start_url="about:blank",
        extra_config=None,
        max_deaths=2,
        daemon=True,
        block=False,
        timeout=2,
        debug=False,
    ):
        if debug:
            logger.setLevel(10)
        self.debug = debug
        self.start_time = time.time()
        self.max_deaths = max_deaths
        self._shutdown = False
        self._use_daemon = daemon
        self._daemon_thread = None
        self._timeout = timeout
        self.ready = False
        self.proc = None
        self.host = host
        self.port = port
        self.server = "http://%s:%s" % (self.host, self.port)
        self.chrome_path = chrome_path or self._get_default_path()
        self.req = tPool()
        self._ensure_port_free()
        self.UA = self.PC_UA if user_agent is None else user_agent
        self.headless = headless
        self.proxy = proxy
        self.disable_image = disable_image
        self._wrap_user_data_dir(user_data_dir)
        self.start_url = start_url
        if extra_config and isinstance(extra_config, str):
            extra_config = [extra_config]
        self.extra_config = extra_config or [
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
        ]
        if not isinstance(self.extra_config, list):
            raise TypeError("extra_config type should be list.")
        self.chrome_proc_start_time = time.time()
        self.launch_chrome()
        if self._use_daemon:
            self.run_forever(block=block)

    def _wrap_user_data_dir(self, user_data_dir):
        """refactor this function to set accurate dir."""
        default_path = os.path.join(os.path.expanduser("~"), "ichrome_user_data")
        user_data_dir = default_path if user_data_dir is None else user_data_dir
        self.user_data_dir = os.path.join(user_data_dir, "chrome_%s" % self.port)
        if not os.path.isdir(self.user_data_dir):
            logger.warning(
                "creating user data dir at [%s]." % os.path.realpath(self.user_data_dir)
            )

    @property
    def ok(self):
        if self.proc_ok and self.connection_ok:
            return True
        return False

    @property
    def proc_ok(self):
        if self.proc and self.proc.poll() is None:
            return True
        return False

    @property
    def connection_ok(self, tries=2):
        url = self.server + "/json"
        for _ in range(tries):
            r = self.req.get(url, timeout=self._timeout)
            if r.x and r.ok:
                self.ready = True
                self.port_in_using.add(self.port)
                return True
            time.sleep(1)
        return False

    @property
    def cmd(self):
        args = [
            self.chrome_path,
            "--remote-debugging-address=%s" % self.host,
            "--remote-debugging-port=%s" % self.port,
        ]
        if self.headless:
            args.append("--headless")
            args.append("--hide-scrollbars")
        if self.user_data_dir:
            args.append("--user-data-dir=%s" % self.user_data_dir)
        if self.UA:
            args.append("--user-agent=%s" % self.UA)
        if self.proxy:
            args.append("--proxy-server=%s" % self.proxy)
        if self.disable_image:
            args.append("--blink-settings=imagesEnabled=false")
        if self.extra_config:
            args.extend(self.extra_config)
        if self.start_url:
            args.append(self.start_url)
        return args

    @property
    def cmd_args(self):
        # list2cmdline for linux use args list failed...
        cmd_string = subprocess.list2cmdline(self.cmd)
        logger.debug("running with: %s" % cmd_string)
        kwargs = {"args": cmd_string, "shell": True}
        if not self.debug:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        return kwargs

    def launch_chrome(self):
        self.proc = subprocess.Popen(**self.cmd_args)
        if self.ok:
            logger.info("launch_chrome success: %s, args: %s" % (self, self.proc.args))
            return True
        else:
            logger.error("launch_chrome failed: %s, args: %s" % (self, self.cmd))
            return False

    def _ensure_port_free(self):
        for _ in range(3):
            try:
                sock = socket.socket()
                sock.connect((self.host, self.port))
                logger.info("shutting down chrome using port %s" % self.port)
                self.kill(True)
                continue
            except ConnectionRefusedError:
                return True
            finally:
                sock.close()
        else:
            raise ValueError("port in used")

    @staticmethod
    def _get_default_path():
        if IS_WINDOWS:
            paths = [
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "%s\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
                % os.getenv("USERPROFILE"),
            ]
            for path in paths:
                if not path:
                    continue
                if os.path.isfile(path):
                    return path
        else:
            paths = ["google-chrome", "google-chrome-stable"]
            for path in paths:
                try:
                    out = subprocess.check_output([path, "--version"], timeout=2)
                    if not out:
                        continue
                    if out.startswith(b"Google Chrome "):
                        return path
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        raise FileNotFoundError("Not found executable chrome file.")

    def _daemon(self, interval=5, max_deaths=None):
        """if chrome proc is killed 3 times too fast (not raise TimeoutExpired),
        will skip auto_restart."""
        return_code = None
        deaths = 0
        max_deaths = max_deaths or self.max_deaths
        while self._use_daemon:
            if self._shutdown:
                logger.info(
                    "%s daemon exited after shutdown(%s)."
                    % (self, ttime(self._shutdown))
                )
                break
            if deaths >= max_deaths:
                logger.info(
                    "%s daemon exited for number of deaths is more than %s."
                    % (self, max_deaths)
                )
                break
            if not self.proc_ok:
                logger.debug("%s daemon is restarting proc." % self)
                self.restart()
                continue
            try:
                return_code = self.proc.wait(timeout=interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
        logger.info("%s daemon exited." % self)

    def run_forever(self, block=True, interval=5, max_deaths=None):
        if self._shutdown:
            raise IOError(
                "%s run_forever failed after shutdown(%s)."
                % (self, ttime(self._shutdown))
            )
        if not self._daemon_thread:
            self._daemon_thread = threading.Thread(
                target=self._daemon,
                kwargs={"interval": interval, "max_deaths": max_deaths},
                daemon=True,
            )
            self._daemon_thread.start()
        logger.debug(
            "%s run_forever(block=%s, interval=%s, max_deaths=%s)."
            % (self, block, interval, max_deaths or self.max_deaths)
        )
        if block:
            self._daemon_thread.join()

    def kill(self, force=False):
        self.ready = False
        if self.proc:
            self.proc.kill()
        if force:
            max_deaths = self.max_deaths
        else:
            max_deaths = 0
        self.clear_chrome_process(self.port, max_deaths=max_deaths)
        self.port_in_using.discard(self.port)

    def restart(self):
        logger.info("restarting %s" % self)
        self.kill()
        return self.launch_chrome()

    def shutdown(self):
        if self._shutdown:
            logger.info(
                "can not shutdown twice, %s has been shutdown at %s"
                % (self, ttime(self._shutdown))
            )
            return
        logger.info(
            "%s shutting down, start-up: %s, duration: %s."
            % (
                self,
                ttime(self.start_time),
                timepass(time.time() - self.start_time, accuracy=3, format=1),
            )
        )
        self._shutdown = time.time()
        self.kill()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()

    @staticmethod
    def clear_chrome_process(port=None, timeout=None, max_deaths=2):
        """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
        set timeout to avoid running forever.
        set max_deaths and port, will return before timeout.
        """
        port = port or ""
        # win32 and linux chrome proc_names
        proc_names = {"chrome.exe", "chrome"}
        killed = []
        port_args = "--remote-debugging-port=%s" % port
        start_time = time.time()
        if timeout is None:
            timeout = max_deaths or 3
        while 1:
            for proc in psutil.process_iter():
                try:
                    pname = proc.name()
                    if pname in proc_names and port_args in " ".join(proc.cmdline()):
                        for cmd in proc.cmdline():
                            if port_args in cmd:
                                logger.debug("kill %s %s" % (pname, cmd))
                                proc.kill()
                                if port:
                                    killed.append(port_args)
                except:
                    pass
            if port and len(killed) >= max_deaths:
                return
            if max_deaths is 0:
                return
            if timeout and time.time() - start_time < timeout:
                time.sleep(1)
                continue
            return

    def __del__(self):
        if not self._shutdown:
            self.shutdown()

    def __str__(self):
        return "%s(%s:%s)" % (self.__class__.__name__, self.host, self.port)


class Chrome(object):
    def __init__(self, host="localhost", port=9222, timeout=2, retry=1):
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
                self.server + "/json", timeout=self.timeout, retry=self.retry
            )
            return [
                Tab(
                    tab["id"],
                    tab["title"],
                    tab["url"],
                    tab["webSocketDebuggerUrl"],
                    self,
                )
                for tab in r.json()
                if tab["type"] == "page"
            ]
        except:
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
            tab_id, title, _url, websocketURL = (
                rjson["id"],
                rjson["title"],
                rjson["url"],
                rjson["webSocketDebuggerUrl"],
            )
            tab = Tab(tab_id, title, _url, websocketURL, self)
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
            "%s/json/version" % self.server, retry=self.retry, timeout=self.timeout
        )
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
    def __init__(self, tab_id, title, url, websocketURL, chrome, timeout=5):
        self.tab_id = tab_id
        self.title = title
        self._url = url
        self.websocketURL = websocketURL
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
        self.ws.connect(self.websocketURL, timeout=self.timeout)

    def activate_tab(self):
        return self.chrome.activate_tab(self.tab_id)

    def close_tab(self):
        return self.chrome.close_tab(self.tab_id)

    def activate(self):
        return self.send("Page.bringToFront")

    def close(self):
        return self.send("Page.setTouchEmulationEnabled")

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

    def send(self, method, timeout=None, callback=None, mute_log=False, **kwargs):
        try:
            timeout = self.timeout if timeout is None else timeout
            request = {"method": method, "params": kwargs}
            self._message_id += 1
            request["id"] = self._message_id
            if not mute_log:
                logger.info("<%s> send: %s" % (self, request))
            with self.lock:
                self.ws.send(json.dumps(request))
            res = self.recv({"id": request["id"]}, timeout=timeout, callback=callback)
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
        except:
            return []

    @property
    def current_url(self):
        return json.loads(self.js("window.location.href"))["result"]["result"]["value"]

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
            logger.error(
                "tab.content error %s:\n%s" % (response, traceback.format_exc())
            )
            return ""

    def wait_loading(self, timeout=None, callback=None):
        data = self.wait_event(
            "Page.loadEventFired", timeout=timeout, callback=callback
        )
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
            result = self.recv({"method": event}, timeout=timeout, callback=callback)
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
                    "Page.navigate", url=url, referrer=referrer, timeout=timeout
                )
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
        return self.send("Runtime.evaluate", expression=javascript, mute_log=mute_log)

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
                "item.result=el.%s || '';item.result=item.result.toString()" % action
            )
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
            logger.info("querySelectorAll error: %s, response: %s" % (e, response))
            if isinstance(index, int):
                return None
            return []

    def inject_js(self, url, timeout=None, retry=0):
        # js_source_code = """
        # var script=document.createElement("script");
        # script.type="text/javascript";
        # script.src="{}";
        # document.getElementsByTagName('head')[0].appendChild(script);
        # """.format(url)
        r = self.req.get(url, verify=0, timeout=timeout, retry=retry)
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
    def __init__(self, tagName, innerHTML, outerHTML, textContent, attributes, result):
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


def main():
    pass


if __name__ == "__main__":
    main()
