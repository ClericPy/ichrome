import psutil
from torequests.versions import IS_WINDOWS
from torequests import tPool
import threading
from torequests.utils import print_info
import os
import json
import subprocess
import socket
import time
import traceback
from queue import Queue
import websocket
from collections import deque


def mute_log():
    # mute the print_info logger
    from torequests.logs import print_logger

    print_logger.setLevel(999)


class ChromeDaemon(object):
    """create chrome process.
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
        port=None,
        headless=False,
        user_agent=None,
        proxy=None,
        user_data_dir=None,
        disable_image=False,
        start_url="about:blank",
        extra_config=None,
        auto_restart=True,
        max_deaths=2,
    ):
        self.proc = None
        self.chrome_path = self._ensure_chrome(chrome_path or self.DEFAULT_CHROME_PATH)
        self.host = host
        self.port = port
        self.server = "http://%s:%s" % (self.host, self.port)
        self.req = tPool()
        self._ensure_port_free()
        self.UA = user_agent or self.DEFAULT_UA
        self.headless = headless
        self.proxy = proxy
        self.disable_image = disable_image
        self.user_data_dir = (
            "../chrome-%s-user-data/" % self.port
            if user_data_dir is None
            else user_data_dir
        )
        self.start_url = start_url
        self.extra_config = extra_config or [
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
        ]
        self.chrome_proc_start_time = time.time()
        self.ready = False
        self.max_deaths = max_deaths
        self.auto_restart = auto_restart
        self.launch_chrome()

    def launch_chrome(self):
        self.proc = subprocess.Popen(**self.cmd_args)
        url = self.server + "/json"
        for _ in range(10):
            r = self.req.get(url, timeout=1)
            if r.x and r.ok:
                self.ready = True
                self.port_in_using.add(self.port)
                print_info("launch_chrome success: %s" % self)
                return
            time.sleep(1)

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
                print_info(
                    "shutting down another chrome instance using port %s" % self.port
                )
                self.kill(True)
                continue
            except ConnectionRefusedError:
                return True
            finally:
                sock.close()
        else:
            raise ValueError("port in used")

    @staticmethod
    def _ensure_chrome(chrome_path):
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
                        print_info("using chrome path: %s." % (path))
                    return path
            else:
                raise FileNotFoundError("Bad chrome path.")
        else:
            path = chrome_path or "google-chrome"
            out = subprocess.check_output([path, "--version"], timeout=2)
            if out.startswith(b"Google Chrome "):
                if chrome_path and chrome_path != path:
                    print_info("using chrome path: %s." % (path))
                return path

    @property
    def cmd(self):
        args = [
            self.chrome_path,
            "--remote-debugging-address=%s" % self.host,
            "--remote-debugging-port=%s" % self.port,
        ]
        if self.headless:
            args.append(self.headless)
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

    @property
    def alive(self):
        if self.proc:
            return self.proc.poll() is None
        return False

    def daemon(self, interval=5, max_deaths=None):
        """if chrome proc is killed 3 times too fast (not raise TimeoutExpired),
        will skip auto_restart."""
        return_code = None
        deaths = 0
        max_deaths = max_deaths or self.max_deaths
        while 1:
            try:
                return_code = self.proc.wait(timeout=interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
            if deaths >= max_deaths:
                break
            if not self.alive and self.auto_restart:
                self.restart()
                continue
        else:
            print_info("exit daemon")

    def run_forever(self, block=True):
        t = threading.Thread(target=self.daemon, daemon=True)
        t.start()
        if block:
            t.join()

    def kill(self, force=False, cycle=5):
        self.ready = False
        if self.proc:
            self.proc.kill()
        if force:
            self.clear_chrome_process(self.port, timeout=5)
        else:
            self.clear_chrome_process(self.port)
        self.port_in_using.add(self.port)

    def restart(self):
        self.kill()
        self.launch_chrome()

    def shutdown(self):
        print_info("shut down %s." % self)
        self.auto_restart = False
        self.kill()

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
                                print_info("kill %s %s" % (pname, cmd))
                                proc.kill()
                except:
                    pass
            if timeout and time.time() - start_time < timeout:
                time.sleep(1)
                continue
            return

    def __del__(self):
        print_info("%s.__del__()." % self)
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

    def __str__(self):
        return "[Chromote(tabs=%d)]" % len(self.tabs)

    def __repr__(self):
        return "Chromote(%s)" % (self.server)


class Tab(object):
    def __init__(self, tid, title, url, websocketURL, chrome, timeout=None):
        self.tid = tid
        self.title = title
        self.url = url
        self.websocketURL = websocketURL
        self.chrome = chrome
        self.timeout = timeout

        self._message_id = 0
        self._watchers = []
        self.lock = threading.Lock()
        self.ws = websocket.WebSocket()
        self._connect()
        for job in [self._recv_daemon, self._queue_watcher]:
            t = threading.Thread(target=self._recv_daemon, daemon=True)
            t.start()

    def _connect(self):
        self.ws.connect(self.websocketURL, timeout=self.timeout)

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
                data = self.ws.recv()
                data = json.loads(data)
                for item in self._watchers:
                    # TODO 等实现接收器, 并且要清理掉 _watcher
                    if item[0] in data.items():
                        item[1].send(data)

                # self._message_queue.put({"ts": int(time.time()), "msg": self.ws.recv()})
            except websocket._exceptions.WebSocketConnectionClosedException:
                break

    def _recv(self, arg, timeout=None):
        # TODO 这里注册了事件以后, 要监听 Timeout 时间内如果触发, 拿到返回值
        timeout = timeout or self.timeout
        # 等待超时的一个接收器, 要么超时, 要么提前收到结果, 考虑生成器或者队列
        # 
        listener = None
        arg = tuple(arg.items())[0]
        self._watchers.append([arg, listener])

    def _send(self, request):
        for _ in range(3):
            try:
                self._message_id += 1
                request["id"] = self._message_id
                with self.lock:
                    self.ws.send(json.dumps(request))
                res = self.recv({"id": request["id"]})
                return res
            except (
                websocket._exceptions.WebSocketTimeoutException,
                websocket._exceptions.WebSocketConnectionClosedException,
            ):
                self.refresh_ws()

    def refresh_ws(self):
        self.ws.close()
        self._connect()

    @property
    def now(self):
        return int(time.time())

    def clear_cookies(self):
        return self._send({"method": "Network.clearBrowserCookies"})

    @property
    def html(self):
        try:
            result = json.loads(self.js("document.documentElement.outerHTML"))
            value = result["result"]["result"]["value"]
            return value.encode("utf-8")
        except KeyError:
            print_info(traceback.format_exc())
            return ""

    def _wait_loading(self):
        data = self._wait_event("Page.loadEventFired")
        return data

    def _wait_event(self, event=None):
        # block
        timeout = 6
        start_time = time.time()
        ws = ws or self.ws
        data = None
        while time.time() - start_time < timeout:
            try:
                data = ws.recv()
                if not data:
                    continue
                data = json.loads(data)
                if not event or data.get("method") == event:
                    return data
            except (
                websocket._exceptions.WebSocketTimeoutException,
                websocket._exceptions.WebSocketConnectionClosedException,
            ):
                return None
            # except Exception as e:
            # print('wait event %s failed for %s' % (event, e))

    def reload(self, timeout=5):
        """
        Reload the page
        """
        return self.set_url(timeout=timeout)

    def set_url(self, url=None, timeout=5):
        """
        Navigate the tab to the URL, 
        """
        ws = self.connect(timeout)
        self._send({"method": "Page.enable"})
        if url:
            self.url = url
            data = self._send({"method": "Page.navigate", "params": {"url": url}})
        else:
            data = self._send({"method": "Page.reload"})
        if self._wait_loading(ws=ws) is None:
            self._send({"method": "Page.stopLoading"})
        ws.close()
        return data

    def js(self, javascript):
        """
        Evaluate JavaScript on the page
        """
        return self._send(
            {"method": "Runtime.evaluate", "params": {"expression": javascript}}
        )

    def __str__(self):
        return "Tab(%s)" % (self.url)

    def __repr__(self):
        return 'ChromeTab("%s", "%s", "%s", port: %s)' % (
            self.tid,
            self.title,
            self.url,
            self.chrome.port,
        )

    def __del__(self):
        with self.lock:
            self.ws.close()


def main():
    # chrome = ChromeLauncher(port=9222)
    # # Launcher
    # # time.sleep(3000)
    # chrome.run_forever()
    chrome = Chrome()
    tab = chrome.tabs[0]
    print(tab)


if __name__ == "__main__":
    main()
