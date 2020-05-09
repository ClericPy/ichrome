# -*- coding: utf-8 -*-
import asyncio
import os
import platform
import socket
import subprocess
import threading
import time
from pathlib import Path

import psutil
from torequests import tPool
from torequests.aiohttp_dummy import Requests
from torequests.utils import timepass, ttime

from .logs import logger
"""
Sync / block operations for launching chrome processes.
"""


class ChromeDaemon(object):
    """Create chrome process, and auto restart if it crash too fast.
    max_deaths: max_deaths=2 means should quick shutdown chrome twice to skip auto_restart. Default 1.

        chrome_path=None,     chrome executable file path, default to null for
                              automatic searching
        host="127.0.0.1",     --remote-debugging-address, default to 127.0.0.1
        port,                 --remote-debugging-port, default to 9222
        headless,             --headless and --hide-scrollbars, default to False
        user_agent,           --user-agent, default to 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36'
        proxy,                --proxy-server, default to None
        user_data_dir,        user_data_dir to save the user data, default to ~/ichrome_user_data
        disable_image,        disable image for loading performance, default to False
        start_url,            start url while launching chrome, default to about:blank
        max_deaths,           max deaths in 5 secs, auto restart `max_deaths` times if crash fast in 5 secs. default to 1 for without auto-restart
        timeout,              timeout to connect the remote server, default to 1 for localhost
        debug,                set logger level to DEBUG
        proc_check_interval,  check chrome process alive every interval seconds

    default extra_config: ["--disable-gpu", "--no-sandbox", "--no-first-run"]

    common args:

        --incognito: Causes the browser to launch directly in incognito mode
        --mute-audio: Mutes audio sent to the audio device so it is not audible during automated testing.
        --blink-settings=imagesEnabled=false: disable image loading.

        --no-sandbox: headless mode will need this arg.
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

    see more args: https://peter.sh/experiments/chromium-command-line-switches/
    """

    port_in_using: set = set()
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
        timeout=1,
        debug=False,
        proc_check_interval=5,
    ):
        if debug:
            logger.setLevel('DEBUG')
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
        self.server = f"http://{self.host}:{self.port}"
        self.chrome_path = chrome_path
        self.UA = self.PC_UA if user_agent is None else user_agent
        self.headless = headless
        self.proxy = proxy
        self.disable_image = disable_image
        self._wrap_user_data_dir(user_data_dir)
        self.start_url = start_url
        if extra_config and isinstance(extra_config, str):
            extra_config = [extra_config]
        self.extra_config = extra_config or ["--disable-gpu", "--no-first-run"]
        if not isinstance(self.extra_config, list):
            raise TypeError("extra_config type should be list.")
        self.chrome_proc_start_time = time.time()
        self.proc_check_interval = proc_check_interval
        self.init(block)

    def init(self, block):
        self.chrome_path = self.chrome_path or self._get_default_path()
        self._ensure_port_free()
        self.req = tPool()
        self.launch_chrome()
        if self._use_daemon:
            self._daemon_thread = self.run_forever(block=block)

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

    def _wrap_user_data_dir(self, user_data_dir):
        """refactor this function to set accurate dir."""
        if user_data_dir is None:
            user_data_dir = Path.home() / 'ichrome_user_data'
        else:
            user_data_dir = Path(user_data_dir)
        self.user_data_dir = user_data_dir / f"chrome_{self.port}"
        if not self.user_data_dir.is_dir():
            logger.warning(
                f"creating user data dir at [{os.path.realpath(self.user_data_dir)}]."
            )
            self.ensure_dir(self.user_data_dir)

    @classmethod
    def clear_user_dir(cls, user_data_dir):
        return cls.clear_dir(user_data_dir)

    @classmethod
    def clear_dir(cls, dir_path):
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.info(f'Dir is not exist: {dir_path}.')
            return True
        logger.info(f'Cleaning {dir_path}...')
        for f in dir_path.iterdir():
            if f.is_dir():
                cls.clear_dir(f)
            else:
                f.unlink()
                logger.info(f'File removed: {f}')
        dir_path.rmdir()
        logger.info(f'Folder removed: {dir_path}')

    @property
    def ok(self):
        return self.proc_ok and self.connection_ok

    @property
    def proc_ok(self):
        if self.proc and self.proc.poll() is None:
            return True
        return False

    @property
    def connection_ok(self):
        url = self.server + "/json"
        for _ in range(2):
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
            f"--remote-debugging-address={self.host}",
            f"--remote-debugging-port={self.port}",
        ]
        if self.headless:
            args.append("--headless")
            args.append("--hide-scrollbars")
        if self.user_data_dir:
            args.append(f"--user-data-dir={self.user_data_dir}")
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

    @property
    def cmd_args(self):
        # list2cmdline for linux use args list failed...
        cmd_string = subprocess.list2cmdline(self.cmd)
        logger.debug(f"running with: {cmd_string}")
        kwargs = {"args": cmd_string, "shell": True}
        if not self.debug:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        return kwargs

    def _start_chrome_process(self):
        self.proc = subprocess.Popen(**self.cmd_args)

    def launch_chrome(self):
        self._start_chrome_process()
        return self.check_chrome_ready()

    def check_chrome_ready(self):
        if self.ok:
            logger.info(
                f"launch_chrome success: {self}, args: {self.proc.args}")
            return True
        else:
            logger.error(f"launch_chrome failed: {self}, args: {self.cmd}")
            return False

    def _ensure_port_free(self):
        for _ in range(3):
            try:
                sock = socket.socket()
                sock.settimeout(self._timeout)
                sock.connect((self.host, self.port))
                logger.info(f"shutting down chrome using port {self.port}")
                self.kill(True)
                continue
            except (ConnectionRefusedError, socket.timeout):
                return True
            finally:
                sock.close()
        else:
            raise ValueError("port in used")

    @staticmethod
    def _get_default_path():
        current_platform = platform.system()
        if current_platform == 'Windows':
            paths = [
                "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                f"{os.getenv('USERPROFILE')}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
            ]
            for path in paths:
                if not path:
                    continue
                if os.path.isfile(path):
                    return path
        else:
            if current_platform == 'Linux':
                paths = ["google-chrome", "google-chrome-stable"]
            elif current_platform == 'Darwin':
                paths = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                ]
            else:
                raise SystemError(
                    "unknown platform, not found the default chrome path.")
            for path in paths:
                try:
                    out = subprocess.check_output([path, "--version"],
                                                  timeout=2)
                    if not out:
                        continue
                    if out.startswith(b"Google Chrome "):
                        return path
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
        raise FileNotFoundError("Not found executable chrome file.")

    def _daemon(self, interval=None):
        """if chrome proc is killed self.max_deaths times too fast (not raise TimeoutExpired),
        will skip auto_restart.
        check alive every `interval` seconds."""
        interval = interval or proc_check_interval
        return_code = None
        deaths = 0
        while self._use_daemon:
            if self._shutdown:
                logger.info(
                    f"{self} daemon break after shutdown({ttime(self._shutdown)})."
                )
                break
            if deaths >= self.max_deaths:
                logger.info(
                    f"{self} daemon break for deaths is more than {self.max_deaths} times."
                )
                break
            if not self.proc_ok:
                logger.debug(f"{self} daemon is restarting proc.")
                self.restart()
                continue
            try:
                return_code = self.proc.wait(timeout=interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
        logger.info(f"{self} daemon exited.")
        self._shutdown = time.time()
        return return_code

    def run_forever(self, block=True, interval=None):
        interval = interval or self.proc_check_interval
        if self._shutdown:
            raise IOError(
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
            self.proc.terminate()
            try:
                self.proc.wait(1)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if force:
            max_deaths = self.max_deaths
        else:
            max_deaths = 0
        self.clear_chrome_process(self.port, max_deaths=max_deaths)
        self.port_in_using.discard(self.port)

    def restart(self):
        logger.info(f"restarting {self}")
        self.kill()
        return self.launch_chrome()

    def shutdown(self):
        if self._shutdown:
            logger.info(f"{self} shutdown at {ttime(self._shutdown)} yet.")
            return
        logger.info(
            f"{self} shutting down, start-up: {ttime(self.start_time)}, duration: {timepass(time.time() - self.start_time, accuracy=3, format=1)}."
        )
        self._shutdown = time.time()
        self.kill()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if not self._shutdown:
            self.shutdown()

    @staticmethod
    def get_proc(port):
        port_args = f"--remote-debugging-port={port}"
        # win32 and linux chrome proc_names
        proc_names = {"chrome.exe", "chrome"}
        procs = []
        for proc in psutil.process_iter():
            try:
                pname = proc.name()
                if pname in proc_names and port_args in ' '.join(
                        proc.cmdline()):
                    procs.append(proc)
            except Exception:
                pass
        return procs

    @classmethod
    def clear_chrome_process(cls,
                             port=None,
                             timeout=None,
                             max_deaths=1,
                             interval=0.5):
        """kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
        set timeout to avoid running forever.
        set max_deaths and port, will return before timeout.
        """
        port = port or ""
        killed_count = 0
        start_time = time.time()
        if timeout is None:
            timeout = max_deaths or 3
        while 1:
            procs = cls.get_proc(port)
            for proc in procs:
                logger.debug(f"killing {proc}, port: {port}")
                try:
                    proc.kill()
                except psutil._exceptions.NoSuchProcess:
                    continue
            if port:
                if procs:
                    killed_count += 1
                if killed_count >= max_deaths:
                    return
            if max_deaths == 0:
                return
            if timeout and time.time() - start_time < timeout:
                time.sleep(interval)
                continue
            return

    def __del__(self):
        if not self._shutdown:
            self.shutdown()

    def __str__(self):
        return f"{self.__class__.__name__}({self.host}:{self.port})"


class AsyncChromeDaemon(ChromeDaemon):

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
        timeout=1,
        debug=False,
    ):
        super().__init__(chrome_path=chrome_path,
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
                         debug=debug)

    def init(self, block):
        # Please init AsyncChromeDaemon in a running loop with `async with`
        self.req = Requests()
        self._block = block

    async def _init_chrome_daemon(self):
        await self.loop.run_in_executor(None, self._ensure_port_free)
        if not self.chrome_path:
            self.chrome_path = await self.loop.run_in_executor(
                None, self._get_default_path)
        await self.launch_chrome()
        if self._use_daemon:
            self._daemon_thread = await self.run_forever(block=self._block)

    def _start_chrome_process(self):
        self.proc = subprocess.Popen(**self.cmd_args)

    async def launch_chrome(self):
        await self.loop.run_in_executor(None, self._start_chrome_process)
        return await self.ok

    async def check_connection(self):
        url = self.server + "/json"
        for _ in range(int(self._timeout) + 1):
            r = await self.req.get(url, timeout=self._timeout)
            if r and r.ok:
                self.ready = True
                self.port_in_using.add(self.port)
                return True
            await asyncio.sleep(1)
        return False

    @property
    def connection_ok(self):
        # awaitable property
        return self.check_connection()

    @property
    def ok(self):
        # awaitable property
        return self.check_chrome_ready()

    async def check_chrome_ready(self):
        if self.proc_ok and await self.check_connection():
            logger.info(
                f"launch_chrome success: {self}, args: {self.proc.args}")
            return True
        else:
            logger.error(f"launch_chrome failed: {self}, args: {self.cmd}")
            return False

    @property
    def loop(self):
        return asyncio.get_running_loop()

    async def run_forever(self, block=True, interval=None):
        interval = interval or self.proc_check_interval
        if self._shutdown:
            raise IOError(
                f"{self} run_forever failed after shutdown({ttime(self._shutdown)})."
            )
        logger.debug(
            f"{self} run_forever(block={block}, interval={interval}, max_deaths={self.max_deaths})."
        )
        task = self._daemon_thread or asyncio.ensure_future(
            self._daemon(interval=interval))
        if self._block:
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
                logger.info(
                    f"{self} daemon break after shutdown({ttime(self._shutdown)})."
                )
                break
            if deaths >= self.max_deaths:
                logger.info(
                    f"{self} daemon break for deaths is more than {self.max_deaths} times."
                )
                break
            if not self.proc_ok:
                logger.debug(f"{self} daemon is restarting proc.")
                await self.loop.run_in_executor(None, self.restart)
                continue
            try:
                return_code = await self.loop.run_in_executor(
                    None, self.proc.wait, self.interval)
                deaths += 1
            except subprocess.TimeoutExpired:
                deaths = 0
        logger.info(f"{self} daemon exited.")
        self._shutdown = time.time()
        return return_code

    async def __aenter__(self):
        await self._init_chrome_daemon()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.loop.run_in_executor(None, self.__exit__)


class ChromeWorkers:

    def __init__(self, args, kwargs):
        self.args = args
        self.kwargs = kwargs
        self.daemons = []

    async def __aenter__(self):
        return await self.create_chrome_workers()

    async def create_chrome_workers(self):
        for port in range(self.args.port, self.args.port + self.args.workers):
            self.daemons.append(await
                                AsyncChromeDaemon(port=port,
                                                  daemon=True,
                                                  block=False,
                                                  **self.kwargs).__aenter__())

    async def __aexit__(self, *args):
        for daemon in self.daemons:
            await daemon._daemon_thread
            await daemon.__aexit__()

    @classmethod
    async def run_chrome_workers(cls, args, kwargs):
        async with cls(args, kwargs):
            pass
