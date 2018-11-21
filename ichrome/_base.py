import psutil
from torequests.versions import IS_WINDOWS
from torequests import tPool
import threading
from torequests.utils import print_info
import os
import subprocess
import socket
import time


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
        max_deaths=3,
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
                if self.req.get(self.server + "/json", timeout=2).x.ok:
                    print_info(
                        "shutting down another chrome instance using port %s"
                        % self.port
                    )
                self.kill()
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
        """if be kill 3 times too fast (not raise TimeoutExpired),
        will skip the auto_restart logic."""
        return_code = None
        deaths = 0
        max_deaths = max_deaths or self.max_deaths
        while deaths < max_deaths:
            try:
                return_code = self.proc.wait(timeout=interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
            if not self.alive and self.auto_restart:
                self.restart()
                continue
        else:
            print_info("exit daemon")

    def run_forever(self):
        t = threading.Thread(target=self.daemon, daemon=True)
        t.start()
        t.join()

    def kill(self):
        print_info("shut down %s." % self)
        self.ready = False
        if self.proc:
            self.proc.kill()
        self.clear_chrome_process(self.port)
        self.port_in_using.add(self.port)

    def restart(self):
        self.kill()
        self.launch_chrome()

    @staticmethod
    def clear_chrome_process(port=None, cycle=1, interval=2):
        """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port
        set `cycle = 3 (>=max_deaths)` make auto_restart lose efficacy.
        """
        port = port or ""
        # win32 and linux chrome proc_names
        proc_names = {"chrome.exe", "chrome"}
        port_args = "--remote-debugging-port=%s" % port
        for _ in range(cycle):
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
            if cycle > 1:
                time.sleep(interval)

    def __del__(self):
        print_info("deleting %s." % self)
        self.kill()

    def __str__(self):
        return "%s(%s:%s)" % (self.__class__.__name__, self.host, self.port)


class Chrome(object):
    def __init__(self, host="localhost", port=9222):
        self._host = host
        self._port = port
        self._url = "http://%s:%d" % (self.host, self.port)
        self._errmsg = (
            "Connect error! Is Chrome running with -remote-debugging-port=%d"
            % self.port
        )
        self._connect()

    def _connect(self):
        """
        Test connection to browser
        """
        try:
            requests.get(self.url, timeout=3)
        except RequestException:
            raise RequestException(self._errmsg)

    def _get_tabs(self):
        """
        Get all open browser tabs that are pages tabs
        """
        try:
            r = req.get(self.url + "/json", timeout=2, retry=2)
            # print(self.url + "/json")
            # print(r.x)
            # print(r.json(), 111111111)
            return [
                ChromeTab(
                    tab["id"],
                    tab["title"],
                    tab["url"],
                    tab["webSocketDebuggerUrl"],
                    self.host,
                    self.port,
                )
                for tab in r.json()
                if tab["type"] == "page"
            ]
        except:
            traceback.print_exc()
            return []

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    @property
    def url(self):
        return self._url

    @property
    def tabs(self):
        return tuple(self._get_tabs())

    def __len__(self):
        return len(self.tabs)

    def __str__(self):
        return "[Chromote(tabs=%d)]" % len(self)

    def __repr__(self):
        return 'Chromote(host="%s", port=%s)' % (self.host, self.port)

    def __getitem__(self, i):
        return self.tabs[i]

    def __iter__(self):
        return iter(self.tabs)


class Tab(object):
    pass


def main():
    # chrome = ChromeLauncher(port=9222)
    # # Launcher
    # # time.sleep(3000)
    # chrome.run_forever()
    # chrome = Chrome()
    ChromeDaemon.clear_chrome_process(cycle=3)


if __name__ == "__main__":
    main()
