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
    DEFAULT_CHROME_PATH = None
    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36"

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
        timeout=2,
    ):
        self.start_time = time.time()
        self.max_deaths = max_deaths
        self._shutdown = False
        self._use_daemon = daemon
        self._daemon_thread = None
        self._timeout = timeout
        self.ready = False
        self.proc = None

        self.chrome_path = self._ensure_chrome_path(
            chrome_path or self.DEFAULT_CHROME_PATH
        )
        self.host = host
        self.port = port
        self.server = "http://%s:%s" % (self.host, self.port)
        self.req = tPool()
        self._ensure_port_free()
        self.UA = user_agent or self.DEFAULT_UA
        self.headless = headless
        self.proxy = proxy
        self.disable_image = disable_image
        self._wrap_user_data_dir(user_data_dir)
        self.start_url = start_url
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
            self.run_forever(block=False)

    def _wrap_user_data_dir(self, user_data_dir):
        """refactor this function to set accurate dir."""
        user_data_dir = (
            "./ichrome_user_data/" if user_data_dir is None else user_data_dir
        )
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

    def launch_chrome(self):
        self.proc = subprocess.Popen(**self.cmd_args)
        if self.ok:
            logger.info("launch_chrome success: %s" % self)
            return True
        else:
            logger.error("launch_chrome failed: %s" % self)
            return False

    @property
    def cmd_args(self):
        return {
            "args": self.cmd,
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }

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
    def _ensure_chrome_path(chrome_path):
        if IS_WINDOWS:
            backup = [
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
            ]
            paths = [chrome_path] + backup
            for path in paths:
                if not path:
                    continue
                if os.path.isfile(path):
                    cmd = 'wmic datafile where name="%s" get Version /value' % (
                        path.replace("/", "\\\\")
                    )
                    out = subprocess.check_output(cmd, timeout=2)
                    if not (out and out.strip().startswith(b"Version=")):
                        continue
                    if chrome_path and chrome_path != path:
                        logger.debug("using chrome path: %s." % path)
                    return path
            else:
                raise FileNotFoundError("Bad chrome path.")
        else:
            path = chrome_path or "google-chrome"
            out = subprocess.check_output([path, "--version"], timeout=2)
            if out.startswith(b"Google Chrome "):
                if chrome_path and chrome_path != path:
                    logger.debug("using chrome path: %s." % path)
                return path
        logger.error("bad chrome_path: %s" % chrome_path)

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
            args.append('--user-agent="%s"' % self.UA)
        if self.proxy:
            args.append('--proxy-server="%s"' % self.proxy)
        if self.disable_image:
            args.append("--blink-settings=imagesEnabled=false")
        if self.start_url:
            args.append(self.start_url)
        return args

    def _daemon(self, interval=5, max_deaths=None):
        """if chrome proc is killed 3 times too fast (not raise TimeoutExpired),
        will skip auto_restart."""
        return_code = None
        deaths = 0
        max_deaths = max_deaths or self.max_deaths
        while self._use_daemon:
            if self._shutdown:
                logger.info("%s daemon exited after shutdown." % self)
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
            raise IOError("%s run_forever failed after shutdown." % self)
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

    def kill(self, force=False, cycle=5):
        self.ready = False
        if self.proc:
            self.proc.kill()
        if force:
            self.clear_chrome_process(self.port, timeout=self.max_deaths + 1)
        else:
            self.clear_chrome_process(self.port)
        self.port_in_using.discard(self.port)

    def restart(self):
        logger.info("restarting %s" % self)
        self.kill()
        return self.launch_chrome()

    def shutdown(self):
        logger.info(
            "%s shutting down, start-up: %s, duration: %s."
            % (
                self,
                ttime(self.start_time),
                timepass(time.time() - self.start_time, accuracy=3, format=1),
            )
        )
        self._shutdown = True
        self.kill()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()

    @staticmethod
    def clear_chrome_process(port=None, timeout=None):
        """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port
        set timeout to ensure chrome not restart (to make auto_restart lose efficacy).
        """
        port = port or ""
        # win32 and linux chrome proc_names
        proc_names = {"chrome.exe", "chrome"}
        port_args = "--remote-debugging-port=%s" % port
        start_time = time.time()
        while 1:
            for proc in psutil.process_iter():
                try:
                    pname = proc.name()
                    if pname in proc_names and port_args in " ".join(proc.cmdline()):
                        for cmd in proc.cmdline():
                            if port_args in cmd:
                                logger.debug("kill %s %s" % (pname, cmd))
                                proc.kill()
                except:
                    pass
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
            tab = Tab(tab_id, title, _url, websocketURL, self, self.timeout)
            tab.create_time = tab.now
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
        self.url = url
        self.websocketURL = websocketURL
        self.chrome = chrome
        self.timeout = timeout

        self.create_time = None
        self._message_id = 0
        self._listener = Listener()
        self.lock = threading.Lock()
        self.ws = websocket.WebSocket()
        self._connect()
        for target in [self._recv_daemon]:
            t = threading.Thread(target=target, daemon=True)
            t.start()

    def _connect(self):
        self.ws.connect(self.websocketURL, timeout=self.timeout)

    def activate(self):
        return self.chrome.activate_tab(self.tab_id)

    def close(self):
        return self.chrome.close_tab(self.tab_id)

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

    def send(self, method, timeout=None, callback=None, **kwargs):
        try:
            timeout = self.timeout if timeout is None else timeout
            request = {"method": method, "params": kwargs}
            self._message_id += 1
            request["id"] = self._message_id
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
            result = f.cx
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

    @property
    def current_url(self):
        return json.loads(self.js("window.location.href"))["result"]["result"]["value"]

    @property
    def content(self):
        """return"""
        response = None
        try:
            response = self.js("document.documentElement.outerHTML")
            if not response:
                return b""
            result = json.loads(response)
            value = result["result"]["result"]["value"]
            return value.encode("utf-8")
        except (KeyError, json.decoder.JSONDecodeError):
            logger.error(
                "tab.content error %s:\n%s" % (response, traceback.format_exc())
            )
            return b""

    def get_html(self, encoding="utf-8"):
        return self.content.decode(encoding)

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

    def set_url(self, url=None, timeout=5):
        """
        Navigate the tab to the URL
        """
        self.send("Page.enable", timeout=0)
        start_load_ts = self.now
        if url:
            self.url = url
            data = self.send("Page.navigate", url=url, timeout=timeout)
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
        return self.send("Runtime.evaluate", expression=javascript)

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
