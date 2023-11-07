# -*- coding: utf-8 -*-
import asyncio
import atexit
import os
import platform
import re
import socket
import subprocess
import threading
import time
from getpass import getuser
from inspect import isawaitable
from json import loads as _json_loads
from pathlib import Path
from typing import List, Set, Union

from torequests import tPool
from torequests.aiohttp_dummy import Requests
from torequests.utils import timepass, ttime

from .async_utils import AsyncChrome, BrowserContext, _SingleTabConnectionManagerDaemon
from .base import (
    CHROME_PROCESS_NAMES,
    async_run,
    clear_chrome_process,
    ensure_awaitable,
    get_dir_size,
    get_memory_by_port,
    get_proc,
    get_readable_dir_size,
    kill_pid,
)
from .exceptions import ChromeException, ChromeRuntimeError, ChromeTypeError
from .logs import logger


class ChromeDaemon(object):
    """Create chrome process, and auto restart if it crash too fast.
    max_deaths: max_deaths=2 means should quick shutdown chrome twice to skip auto_restart. Default 1.

        chrome_path=None,     chrome executable file path, default to null for
                              automatic searching
        host="127.0.0.1",     --remote-debugging-address, default to 127.0.0.1
        port,                 --remote-debugging-port, default to 9222
        headless,             --headless and --hide-scrollbars, default to False
        user_agent,           --user-agent, default to None (with the original UA)
        proxy,                --proxy-server, default to None
        user_data_dir,        user_data_dir to save the user data, default to ~/ichrome_user_data. These strings will ignore user_data_dir arg: {'null', 'None', '/dev/null', "''", '""'}
        disable_image,        disable image for loading performance, default to False
        start_url,            start url while launching chrome, default to None
        max_deaths,           max deaths in 5 secs, auto restart `max_deaths` times if crash fast in 5 secs. default to 1 (without auto-restart)
        timeout,              timeout to connect the remote server, default to 1 for localhost
        debug,                set logger level to DEBUG
        proc_check_interval,  check chrome process alive every interval seconds

        on_startup & on_shutdown: function which handled a ChromeDaemon object while startup or shutdown

    default extra_config: ["--disable-gpu", "--no-first-run"], root user may need append "--no-sandbox"
    https://github.com/GoogleChrome/chrome-launcher/blob/master/docs/chrome-flags-for-tools.md

    common args:

        --incognito: Causes the browser to launch directly in incognito mode
        --mute-audio: Mutes audio sent to the audio device so it is not audible during automated testing.
        --blink-settings=imagesEnabled=false: disable image loading.
        --no-sandbox
        --disable-javascript
        --disable-extensions
        --disable-background-networking
        --safebrowsing-disable-auto-update
        --disable-sync
        --ignore-certificate-errors
        –disk-cache-dir=xxx: Use a specific disk cache location, rather than one derived from the UserDatadir.
        --disk-cache-size: Forces the maximum disk space to be used by the disk cache, in bytes.
        --single-process
        --proxy-pac-url=xxx. Nonsense for headless mode.
        --kiosk
        --window-size=800,600
        --disable-logging
        --disable-component-extensions-with-background-pages
        --disable-default-apps
        --disable-login-animations
        --disable-notifications
        --disable-print-preview
        --disable-prompt-on-repost
        --disable-setuid-sandbox
        --disable-system-font-check
        --disable-dev-shm-usage
        --aggressive-cache-discard
        --aggressive-tab-discard
        --mem-pressure-system-reserved-kb=80000
        --disable-shared-workers
        --disable-gl-drawing-for-tests
        --use-gl=swiftshader
        --disable-canvas-aa
        --disable-2d-canvas-clip-aa
        --disable-breakpad
        --no-zygote
        --disable-reading-from-canvas
        --disable-remote-fonts
        --renderer-process-limit=1
        --disable-hang-monitor
        --disable-client-side-phishing-detection
        --disable-translate
        --password-store=basic
        --disable-popup-blocking
        --no-service-autorun
        --no-default-browser-check
        --autoplay-policy=user-gesture-required
        --disable-device-discovery-notifications
        --disable-component-update
        --disable-domain-reliability
        --enable-automation


    see more args: https://peter.sh/experiments/chromium-command-line-switches/
    """

    PC_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.106 Safari/537.36"
    MAC_OS_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0_1) Version/8.0.1a Safari/728.28.19"
    )
    WECHAT_UA = "Mozilla/5.0 (Linux; Android 5.0; SM-N9100 Build/LRX21V) > AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 > Chrome/37.0.0.0 Mobile Safari/537.36 > MicroMessenger/6.0.2.56_r958800.520 NetType/WIFI"
    IPAD_UA = "Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1"
    MOBILE_UA = "Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Mobile Safari/537.36"
    IGNORE_USER_DIR_FLAGS = {"null", "None", "/dev/null", "''", '""'}
    MAX_WAIT_CHECKING_SECONDS = 15
    DEFAULT_USER_DIR_PATH = Path.home() / "ichrome_user_data"
    DEFAULT_EXTRA_CONFIG = ["--disable-gpu", "--no-first-run"]
    DEFAULT_POPEN_ARGS = {"start_new_session": True}
    LAUNCHED_PIDS: Set[int] = set()

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
        timeout=3,
        debug=False,
        proc_check_interval=5,
        on_startup=None,
        on_shutdown=None,
        before_startup=None,
        after_shutdown=None,
        clear_after_shutdown=False,
        popen_kwargs: dict = None,
    ):
        if debug:
            logger.setLevel("DEBUG")
        self.debug = debug
        self.start_time = time.time()
        self.max_deaths = max_deaths
        self._shutdown = False
        self._shutdown_reason = ""
        self._use_daemon = daemon
        self._daemon_thread = None
        self._timeout = timeout
        self.ready = False
        self.proc = None
        self.host = host
        self.port = port
        self.chrome_path = chrome_path or os.getenv("CHROME_PATH")
        self.UA = user_agent
        self.headless = headless
        self.proxy = proxy
        self.disable_image = disable_image
        self.user_data_dir = user_data_dir
        self.start_url = start_url
        self.extra_config = extra_config
        self.proc_check_interval = proc_check_interval
        self.on_startup = on_startup
        self.on_shutdown = on_shutdown
        self.before_startup = before_startup
        self.after_shutdown = after_shutdown
        self._block = block
        self.clear_after_shutdown = clear_after_shutdown
        self.popen_kwargs = (
            self.DEFAULT_POPEN_ARGS if popen_kwargs is None else popen_kwargs
        )
        self._use_port_dir = False
        self.init()

    @classmethod
    def cleanup_launched_pids(cls):
        for pid in cls.LAUNCHED_PIDS:
            kill_pid(pid)
        cls.LAUNCHED_PIDS.clear()

    def init(self):
        self._init_chrome_daemon()

    def _init_chrome_daemon(self):
        self._init_extra_config()
        self._init_port()
        self._wrap_user_data_dir()
        if not self.chrome_path:
            self.chrome_path = self._get_default_path()
        _chrome_path = Path(self.chrome_path)
        if _chrome_path.is_file():
            CHROME_PROCESS_NAMES.add(_chrome_path.name)
        self._ensure_port_free()
        self.req = tPool()
        if self.before_startup:
            self.before_startup(self)
        self.launch_chrome()
        if self._use_daemon:
            self._daemon_thread = self.run_forever(block=self._block)
        if self.on_startup:
            self.on_startup(self)

    def _init_extra_config(self):
        if self.extra_config and isinstance(self.extra_config, str):
            self.extra_config = [self.extra_config]
        self.extra_config = self.extra_config or self.DEFAULT_EXTRA_CONFIG
        if "--no-sandbox" not in str(self.extra_config) and getuser() == "root":
            self.extra_config.append("--no-sandbox")
        if not isinstance(self.extra_config, list):
            raise ChromeTypeError(
                f"extra_config type should be list, but {type(self.extra_config)} was given."
            )

    def _init_port(self):
        if self.port is None:
            self.port = self.get_free_port(host=self.host)
        self.server = f"http://{self.host}:{self.port}"

    def get_memory(self, attr="uss", unit="MB"):
        """Only support local Daemon. `uss` is slower than `rss` but useful."""
        return get_memory_by_port(port=self.port, attr=attr, unit=unit, host=self.host)

    @staticmethod
    def ensure_dir(path: Path):
        if isinstance(path, str):
            path = Path(path)
        if path.is_dir():
            return path
        else:
            paths = list(reversed(path.parents))
            paths.append(path)
            p: Path
            for p in paths:
                if not p.is_dir():
                    p.mkdir()
            return path

    @staticmethod
    def get_dir_size(path):
        return get_dir_size(path)

    @staticmethod
    def get_readable_dir_size(path):
        return get_readable_dir_size(path)

    @classmethod
    def _ensure_user_dir(cls, user_data_dir):
        if user_data_dir is None:
            # use default path
            env_path = os.getenv("USER_DATA_DIR")
            if env_path:
                return Path(env_path)
            else:
                return cls.DEFAULT_USER_DIR_PATH
        elif isinstance(user_data_dir, Path):
            return user_data_dir
        elif user_data_dir in cls.IGNORE_USER_DIR_FLAGS:
            # ignore custom path settings
            logger.debug(
                "Ignore custom user_data_dir, using default user set by system."
            )
            return None
        else:
            # valid path string
            return Path(re.sub(r"""^['"]|['"]$""", "", str(user_data_dir)))

    def _wrap_user_data_dir(self):
        if "--user-data-dir=" in str(self.extra_config):
            # ignore custom user_data_dir by ichrome
            self.user_data_dir = None
            return
        main_user_dir = self._ensure_user_dir(self.user_data_dir)
        if main_user_dir is None:
            # use the default path and ignore --user-data-dir
            self.user_data_dir = None
            return
        elif (main_user_dir / "Last Browser").is_file():
            # exist user dir, use this one without port folder
            self.user_data_dir = main_user_dir
            return
        else:
            port_user_dir = main_user_dir / f"chrome_{self.port}"
            self.user_data_dir = port_user_dir
            if not self.user_data_dir.is_dir():
                logger.debug(
                    f"creating user data dir at [{os.path.realpath(self.user_data_dir)}]."
                )
                self.user_data_dir.mkdir(parents=True, exist_ok=True)
                self._use_port_dir = True

    @classmethod
    def clear_user_dir(cls, user_data_dir=None, port=None):
        """WARNING: this is a sync class method, if you want to clear only user dir, use self.clear_user_data_dir instead"""
        main_user_dir = cls._ensure_user_dir(user_data_dir)
        if port is None:
            # clear whole ichrome dir if port is None
            cls.clear_dir_with_shutil(main_user_dir)
        else:
            # clear port dir if port is not None
            cls.clear_dir_with_shutil(main_user_dir / f"chrome_{port}")

    def _clear_user_dir(self):
        # Deprecated
        return self.clear_user_data_dir()

    def _clear_user_data_dir(self):
        self.clear_dir_with_shutil(self.user_data_dir)
        if self._use_port_dir:
            main_user_dir = self.user_data_dir.parent
            if main_user_dir.is_dir():
                for sub_file_or_dir in main_user_dir.iterdir():
                    if sub_file_or_dir.exists():
                        break
                else:
                    # remove null main_user_dir
                    main_user_dir.rmdir()

    def clear_user_data_dir(self):
        # clear self user dir
        self.shutdown("_clear_user_dir")
        self._clear_user_data_dir()

    @staticmethod
    def clear_dir_with_shutil(dir_path):
        errors = []

        def onerror(*args):
            errors.append(args[2][1])

        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.debug(f"{dir_path} is not exists, ignore.")
            return
        import shutil

        for _ in range(6):
            try:
                shutil.rmtree(dir_path, onerror=onerror)
                if not dir_path.is_dir():
                    break
                time.sleep(0.5)
                logger.debug(f"clear_dir_with_shutil({dir_path}) error: {errors}")
            except FileNotFoundError as err:
                errors.append(err)
        else:
            if errors:
                logger.debug(
                    f"clear_dir_with_shutil({dir_path}) failed: errors={errors}"
                )

    @classmethod
    def clear_dir(cls, dir_path):
        # please use clear_dir_with_shutil
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.debug(f"{dir_path} not exists, ignore.")
            return
        if not dir_path.is_dir():
            logger.debug(f"{dir_path} is not exist:.")
            return True
        for f in dir_path.iterdir():
            if f.is_dir():
                cls.clear_dir(f)
            else:
                f.unlink()
                logger.debug(f"File removed: {f}")
        dir_path.rmdir()

    @property
    def ok(self):
        return self.proc_ok and self.connection_ok

    @property
    def proc_ok(self):
        return self._proc_ok()

    def _proc_ok(self):
        if self.proc and self.proc.poll() is None:
            return True
        return False

    @property
    def connection_ok(self):
        for _ in range(int(self.MAX_WAIT_CHECKING_SECONDS * 2)):
            r = self.req.head(self.server, timeout=self._timeout)
            if r.x and r.ok:
                self.ready = True
                return True
            time.sleep(0.5)
        return False

    @property
    def cmd(self):
        args = [
            self.chrome_path,
            f"--remote-debugging-address={self.host}",
            f"--remote-debugging-port={self.port}",
        ]
        if self.headless:
            args.append("--headless")
            args.append("--hide-scrollbars")
        if self.user_data_dir:
            # user_data_dir absolute path is faster while running
            args.append(f"--user-data-dir={self.user_data_dir.absolute().as_posix()}")
        if self.UA:
            args.append(f"--user-agent={self.UA}")
        if self.proxy:
            args.append(f"--proxy-server={self.proxy}")
        if self.disable_image:
            args.append("--blink-settings=imagesEnabled=false")
        if self.extra_config:
            args.extend(self.extra_config)
        if self.start_url:
            args.append(self.start_url)
        return args

    def get_cmd_args(self):
        # list2cmdline for linux use args list failed...
        cmd_string = subprocess.list2cmdline(self.cmd)
        logger.debug(f"running with: {cmd_string}")
        kwargs = {"args": cmd_string, "shell": True}
        if not self.debug:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        kwargs.update(self.popen_kwargs)
        self.cmd_args = kwargs
        return kwargs

    def _start_chrome_process(self):
        self.chrome_proc_start_time = time.time()
        self.proc = subprocess.Popen(**self.get_cmd_args())
        self.LAUNCHED_PIDS.add(self.proc.pid)

    def launch_chrome(self):
        self._start_chrome_process()
        error = None
        for _ in range(int(self.MAX_WAIT_CHECKING_SECONDS * 2)):
            if not self.proc_ok:
                error = "launch_chrome failed for proc not ok"
                break
            r = self.req.head(self.server, timeout=self._timeout)
            if r.x and r.ok:
                self.ready = True
                break
            time.sleep(0.5)
        else:
            error = "launch_chrome failed for connection not ok"
        if error:
            logger.error(error)
            raise ChromeRuntimeError(error)

    def check_chrome_ready(self):
        if self.ok:
            logger.debug(f"launch_chrome success: {self}, args: {self.proc.args}")
            return True
        else:
            logger.debug(f"launch_chrome failed: {self}, args: {self.cmd}")
            return False

    @classmethod
    def get_free_port(cls, host="127.0.0.1", start=9222, max_tries=100, timeout=1):
        for offset in range(max_tries):
            port = start + offset
            if cls._check_host_port_in_use(host, port, timeout):
                return port
        raise ChromeRuntimeError(f"No free port beteen {start} and {start+max_tries}")

    @staticmethod
    def _check_host_port_in_use(host="127.0.0.1", port=9222, timeout=1):
        sock = None
        try:
            sock = socket.socket()
            sock.settimeout(timeout)
            sock.connect((host, port))
            return False
        except (ConnectionRefusedError, socket.timeout):
            return True
        finally:
            if sock is not None:
                sock.close()

    def _ensure_port_free(self, max_tries=3):
        for _ in range(max_tries):
            ok = self._check_host_port_in_use(self.host, self.port, self._timeout)
            if ok:
                return True
            logger.debug(f"shutting down chrome using port {self.port}")
            self.kill(True)
        else:
            raise ChromeRuntimeError(f"port in used {self.port} for host {self.host}")

    @classmethod
    def get_chrome_path(cls):
        try:
            return cls._get_default_path()
        except ChromeRuntimeError:
            return None

    @staticmethod
    def _iter_chrome_path():
        current_platform = platform.system()
        if current_platform == "Windows":
            paths = [
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                f"{os.getenv('USERPROFILE')}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
                "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            ]
            for path in paths:
                if not path:
                    continue
                if os.path.isfile(path):
                    yield path
        else:
            if current_platform == "Linux":
                paths = [
                    "google-chrome",
                    "google-chrome-stable",
                    "google-chrome-beta",
                    "google-chrome-dev",
                    "microsoft-edge-stable",
                ]
            elif current_platform == "Darwin":
                paths = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                ]
            else:
                raise ChromeRuntimeError(
                    "unknown platform, could not find the default chrome path."
                )
            for path in paths:
                try:
                    out = subprocess.check_output([path, "--version"], timeout=2)
                    if not out:
                        continue
                    if out.startswith((b"Google Chrome ", b"Microsoft Edge")):
                        yield path
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        raise ChromeRuntimeError("Executable chrome file was not found.")

    @classmethod
    def _get_default_path(cls):
        for path in cls._iter_chrome_path():
            return path
        raise ChromeRuntimeError("Executable chrome file was not found.")

    def _daemon(self, interval=None):
        """if chrome proc is killed self.max_deaths times too fast (not raise TimeoutExpired),
        will skip auto_restart.
        check alive every `interval` seconds."""
        interval = interval or self.proc_check_interval
        return_code = None
        deaths = 0
        while self._use_daemon:
            if self._shutdown:
                logger.debug(
                    f"{self} daemon break after shutdown({ttime(self._shutdown)})."
                )
                break
            elif deaths >= self.max_deaths:
                logger.debug(
                    f"{self} daemon break for deaths is more than {self.max_deaths} times."
                )
                break
            elif not self.proc_ok:
                logger.debug(f"{self} daemon is restarting proc.")
                self.restart()
                deaths += 1
                continue
            try:
                return_code = self.proc.wait(timeout=interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
        logger.debug(
            f"{self} daemon exited for {self._shutdown_reason}. return_code: {return_code}"
        )
        return return_code

    def run_forever(self, block=True, interval=None):
        interval = interval or self.proc_check_interval
        if self._shutdown:
            raise ChromeRuntimeError(
                f"{self} run_forever failed after shutdown({ttime(self._shutdown)})."
            )
        logger.debug(
            f"{self} run_forever(block={block}, interval={interval}, max_deaths={self.max_deaths})."
        )
        if block:
            return self._daemon(interval=interval)
        else:
            if not self._daemon_thread:
                self._daemon_thread = threading.Thread(
                    target=self._daemon,
                    kwargs={"interval": interval},
                    daemon=True,
                )
                self._daemon_thread.start()
            return self._daemon_thread

    def kill(self, force=False):
        self.ready = False
        if self.proc:
            self.proc.kill()
            self.proc.__exit__(None, None, None)
            self.LAUNCHED_PIDS.discard(self.proc.pid)
        if force:
            max_deaths = self.max_deaths
        else:
            max_deaths = 0
        self.clear_chrome_process(self.port, max_deaths=max_deaths, host=self.host)

    def restart(self):
        logger.debug(f"restarting {self}")
        self.kill()
        return self.launch_chrome()

    def update_shutdown_time(self):
        self._shutdown = time.time()

    def shutdown(self, reason=None):
        if self._shutdown:
            logger.debug(f"{self} shutdown at {ttime(self._shutdown)} yet.")
            return
        self._shutdown_reason = reason
        self.update_shutdown_time()
        reason = f" for {reason}" if reason else ""
        logger.debug(
            f"{self} shutting down{reason}, start-up: {ttime(self.start_time)}, duration: {timepass(time.time() - self.start_time, accuracy=3, format=1)}."
        )
        if self.on_shutdown:
            self.on_shutdown(self)
        self.kill(True)
        if self.after_shutdown:
            self.after_shutdown(self)
        if self.clear_after_shutdown:
            self.clear_user_data_dir()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown("__exit__")

    @staticmethod
    def get_proc(port, host=None):
        return get_proc(port, host=host)

    @staticmethod
    def clear_chrome_process(
        port=None, timeout=None, max_deaths=1, interval=0.5, host=None
    ):
        return clear_chrome_process(
            port=port,
            timeout=timeout,
            max_deaths=max_deaths,
            interval=interval,
            host=host,
        )

    def get_local_state(self):
        """Get the dict from {self.user-data-dir}/Local State which including online user profiles info.
        WARNING: return None while self.user_data_dir is not set, and new folder may not have this file until chrome process run more than 10 secs.
        """
        if self.user_data_dir:
            file_path = self.user_data_dir / "Local State"
            if file_path.is_file():
                try:
                    return _json_loads(file_path.read_text())
                except ValueError:
                    pass
        return None

    def __del__(self):
        self.shutdown("__del__")

    def __str__(self):
        return f"{self.__class__.__name__}({self.host}:{self.port})"

    def __repr__(self):
        return str(self)


class AsyncChromeDaemon(ChromeDaemon):
    _demo = r'''

    demo::

        import asyncio
        import json

        from ichrome import AsyncChromeDaemon


        async def main():
            async with AsyncChromeDaemon(clear_after_shutdown=True,
                                        headless=False,
                                        disable_image=False,
                                        user_data_dir='./ichrome_user_data') as cd:
                async with cd.connect_tab(0, auto_close=True) as tab:
                    loaded = await tab.goto('https://httpbin.org/forms/post',
                                            timeout=10)
                    html = await tab.html
                    title = await tab.title
                    print(
                        f'page loaded ok: {loaded}, HTML length is {len(html)}, title is "{title}"'
                    )
                    # try setting the input tag value with JS
                    await tab.js(
                        r"""document.querySelector('[value="bacon"]').checked = true""")
                    # or you can click the checkbox
                    await tab.click('[value="cheese"]')
                    # you can set the value of input
                    await tab.js(
                        r"""document.querySelector('[name="custname"]').value = "1234" """
                    )
                    # now click the submit button
                    await tab.click('form button')
                    await tab.wait_loading(5)
                    # extract the JSON with regex
                    result = await tab.findone(r'<pre.*?>([\s\S]*?)</pre>')
                    print(json.loads(result))


        if __name__ == "__main__":
            asyncio.run(main())

'''
    __doc__ = ChromeDaemon.__doc__ + _demo

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
        timeout=3,
        debug=False,
        proc_check_interval=5,
        on_startup=None,
        on_shutdown=None,
        before_startup=None,
        after_shutdown=None,
        clear_after_shutdown=False,
        popen_kwargs: dict = None,
    ):
        super().__init__(
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
            proc_check_interval=proc_check_interval,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            before_startup=before_startup,
            after_shutdown=after_shutdown,
            clear_after_shutdown=clear_after_shutdown,
            popen_kwargs=popen_kwargs,
        )

    def init(self):
        # Please init AsyncChromeDaemon in a running loop with `async with`
        self._req = None
        self._chrome = AsyncChrome(self.host, self.port, timeout=self._timeout)
        self._init_coro = self._init_chrome_daemon()

    @property
    def req(self):
        if self._req is None:
            raise ChromeRuntimeError("please use Chrome in `async with`")
        return self._req

    async def _init_chrome_daemon(self):
        await async_run(self._init_extra_config)
        await async_run(self._init_port)
        await async_run(self._wrap_user_data_dir)
        if not self.chrome_path:
            self.chrome_path = await async_run(self._get_default_path)
        _chrome_path = Path(self.chrome_path)
        if _chrome_path.is_file():
            CHROME_PROCESS_NAMES.add(_chrome_path.name)
        await async_run(self._ensure_port_free)
        self._req = Requests()
        if self.before_startup:
            await ensure_awaitable(self.before_startup(self))
        await self.launch_chrome()
        if self._use_daemon:
            self._daemon_thread = await self.run_forever(block=self._block)
        if self.on_startup:
            await ensure_awaitable(self.on_startup(self))
        return self

    async def restart(self):
        "restart the chrome process"
        logger.debug(f"restarting {self}")
        await async_run(self.kill)
        return await self.launch_chrome()

    async def launch_chrome(self):
        "launch the chrome with remote-debugging mode"
        await async_run(self._start_chrome_process)
        error = None
        for _ in range(int(self.MAX_WAIT_CHECKING_SECONDS * 2)):
            if not await async_run(self._proc_ok):
                error = "launch_chrome failed for proc not ok"
                break
            if await self._check_chrome_connection():
                self.ready = True
                break
            await asyncio.sleep(0.5)
        else:
            error = "launch_chrome failed for connection not ok"
        if error:
            logger.error(error)
            raise ChromeRuntimeError(error)

    async def _check_chrome_connection(self):
        r = await self.req.head(self.server, timeout=self._timeout)
        return r and r.ok

    async def check_connection(self):
        "check chrome connection ok"
        for _ in range(int(self.MAX_WAIT_CHECKING_SECONDS * 2)):
            if await self._check_chrome_connection():
                self.ready = True
                return True
            await asyncio.sleep(0.5)
        return False

    @property
    def connection_ok(self):
        return self.check_connection()

    @property
    def ok(self):
        return self.check_chrome_ready()

    @classmethod
    async def get_free_port(
        cls, host="127.0.0.1", start=9222, max_tries=100, timeout=1
    ):
        "find a free port which can be used"
        return await async_run(
            super().get_free_port,
            host=host,
            start=start,
            max_tries=max_tries,
            timeout=timeout,
        )

    async def check_ws_ready(self):
        async with self._chrome as chrome:
            return await chrome.check_ws_ready()

    async def check_chrome_ready(self):
        "check if the chrome api is available"
        if self.proc_ok and await self.check_connection():
            logger.debug(f"launch_chrome success: {self}, args: {self.proc.args}")
            return True
        else:
            logger.debug(f"launch_chrome failed: {self}, args: {self.cmd}")
            return False

    @property
    def loop(self):
        return asyncio.get_running_loop()

    async def run_forever(self, block=True, interval=None):
        "start the daemon and ensure proc is alive"
        interval = interval or self.proc_check_interval
        if self._shutdown:
            raise ChromeRuntimeError(
                f"{self} run_forever failed after shutdown({ttime(self._shutdown)})."
            )
        logger.debug(
            f"{self} run_forever(block={block}, interval={interval}, max_deaths={self.max_deaths})."
        )
        task = self._daemon_thread or asyncio.ensure_future(
            self._daemon(interval=interval)
        )
        if block:
            await task
        return task

    async def _daemon(self, interval=None):
        """if chrome proc is killed self.max_deaths times too fast (not raise TimeoutExpired),
        will skip auto_restart.
        check alive every `interval` seconds."""
        interval = interval or self.proc_check_interval
        return_code = None
        deaths = 0
        while self._use_daemon:
            if self._shutdown:
                logger.debug(
                    f"{self} daemon break after shutdown({ttime(self._shutdown)})."
                )
                break
            elif deaths >= self.max_deaths:
                logger.debug(
                    f"{self} daemon break for deaths is more than {self.max_deaths} times."
                )
                break
            elif not self.proc_ok:
                logger.debug(f"{self} daemon is restarting proc.")
                await self.restart()
                deaths += 1
                continue
            try:
                return_code = await async_run(self.proc.wait, interval)
                if self._shutdown_reason:
                    break
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
        logger.debug(
            f"{self} daemon exited for {self._shutdown_reason}. return_code: {return_code}"
        )
        return return_code

    async def __aenter__(self):
        return await self._init_coro

    async def __aexit__(self, *args, **kwargs):
        await self.shutdown("__aexit__")

    @property
    def x(self):
        # `await self.x` to block until chrome daemon loop finished.
        if isawaitable(self._daemon_thread):
            return self._daemon_thread
        else:
            return asyncio.sleep(0)

    async def shutdown(self, reason=None):
        "shutdown the chrome, but do not use it, use async with instead."
        if self._shutdown:
            # logger.debug(f"{self} shutdown at {ttime(self._shutdown)} yet.")
            return
        self._shutdown_reason = reason
        self.update_shutdown_time()
        reason = f" for {reason}" if reason else ""
        logger.debug(
            f"{self} shutting down{reason}, start-up: {ttime(self.start_time)}, duration: {timepass(time.time() - self.start_time, accuracy=3, format=1)}."
        )
        if self.on_shutdown:
            await ensure_awaitable(self.on_shutdown(self))
        await async_run(self.kill, True)
        if self.after_shutdown:
            await ensure_awaitable(self.after_shutdown(self))
        if self.clear_after_shutdown:
            await self.clear_user_data_dir()

    async def _clear_user_dir(self):
        # Deprecated
        return await self.clear_user_data_dir()

    async def clear_user_data_dir(self):
        await self.shutdown("_clear_user_dir")
        return await async_run(self._clear_user_data_dir)

    def connect_tab(
        self,
        index: Union[None, int, str] = 0,
        auto_close: bool = False,
        flatten: bool = None,
    ):
        """More easier way to init a connected Tab with `async with`.

        Got a connected Tab object by using `async with chromed.connect_tab(0) as tab:`

            index = 0 means the current tab.
            index = None means create a new tab.
            index = 'http://python.org' means create a new tab with url.
            index = 'F130D0295DB5879791AA490322133AFC' means the tab with this id.

            If auto_close is True: close this tab while exiting context.

            View more about flatten: https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-attachToTarget"""
        return _SingleTabConnectionManagerDaemon(
            host=self.host,
            port=self.port,
            index=index,
            auto_close=auto_close,
            flatten=flatten,
        )

    async def close_browser(self):
        "close browser peacefully"
        try:
            async with self.connect_tab(0) as tab:
                await tab.close_browser()
                return True
        except ChromeException:
            return False

    async def get_local_state(self):
        return await async_run(super().get_local_state)

    def create_context(
        self,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
    ) -> BrowserContext:
        "create a new browser context, which can be set new proxy, same like the incognito mode"
        return BrowserContext(
            chrome=AsyncChrome(host=self.host, port=self.port, timeout=self._timeout),
            disposeOnDetach=disposeOnDetach,
            proxyServer=proxyServer,
            proxyBypassList=proxyBypassList,
            originsWithUniversalNetworkAccess=originsWithUniversalNetworkAccess,
        )

    def incognito_tab(
        self,
        url: str = "about:blank",
        width: int = None,
        height: int = None,
        enableBeginFrameControl: bool = None,
        newWindow: bool = None,
        background: bool = None,
        disposeOnDetach: bool = True,
        proxyServer: str = None,
        proxyBypassList: str = None,
        originsWithUniversalNetworkAccess: List[str] = None,
        flatten: bool = None,
    ):
        "create a new tab with incognito mode, this is really a good choice"
        chrome = AsyncChrome(host=self.host, port=self.port, timeout=self._timeout)
        return chrome.incognito_tab(
            url=url,
            width=width,
            height=height,
            enableBeginFrameControl=enableBeginFrameControl,
            newWindow=newWindow,
            background=background,
            flatten=flatten,
            disposeOnDetach=disposeOnDetach,
            proxyServer=proxyServer,
            proxyBypassList=proxyBypassList,
            originsWithUniversalNetworkAccess=originsWithUniversalNetworkAccess,
        )

    def __del__(self):
        pass


class ChromeWorkers:
    def __init__(self, start_port=9222, workers=1, kwargs=None):
        self.start_port = start_port or 9222
        self.workers = workers or 1
        self.kwargs = kwargs or {}
        self.daemons = []
        self.tasks = []

    async def __aenter__(self):
        return await self.create_chrome_workers()

    async def start_daemon(self, cd):
        async with cd:
            await cd._daemon_thread

    async def create_chrome_workers(self):
        for port in range(self.start_port, self.start_port + self.workers):
            logger.debug("ChromeDaemon cmd args: port=%s, %s" % (port, self.kwargs))
            cd = AsyncChromeDaemon(port=port, **self.kwargs)
            self.daemons.append(cd)
            self.tasks.append(asyncio.ensure_future(self.start_daemon(cd)))
        return self

    async def wait(self):
        for task in self.tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def __aexit__(self, *args):
        for daemon in self.daemons:
            await daemon.shutdown("__aexit__")

    @classmethod
    async def run_chrome_workers(cls, start_port, workers, kwargs):
        async with cls(start_port, workers, kwargs) as cd:
            await cd.wait()


atexit.register(ChromeDaemon.cleanup_launched_pids)
