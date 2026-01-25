import asyncio
import random
import re
import time
import typing
from base64 import b64decode
from copy import deepcopy
from dataclasses import asdict
from fnmatch import fnmatchcase
from functools import partial

from . import AsyncChromeDaemon, AsyncTab
from .base import Tag, ensure_awaitable
from .exceptions import ChromeException
from .logs import logger
from .schemas.engine_schema import (
    DownloadDTO,
    DownloadResult,
    JsDTO,
    ScreenshotDTO,
    TabConfigDTO,
    TabPrepareDTO,
    TabWaitDTO,
)


class CallbackProtocol(typing.Protocol):
    @staticmethod
    async def __call__(
        tab: "AsyncTab", data: typing.Any, task: "ChromeTask"
    ) -> typing.Any:
        pass


class ChromeTask(asyncio.Future):
    """ExpireFuture"""

    _ID = 0
    MAX_TIMEOUT = 60 * 5
    MAX_TRIES = 3
    EXEC_GLOBALS: typing.Dict[str, typing.Any] = {}
    STOP_SIG = object()

    def __init__(
        self,
        data: typing.Any,
        tab_callback: typing.Optional[CallbackProtocol] = None,
        timeout=None,
        port: typing.Optional[int] = None,
        tab_config: typing.Optional[TabConfigDTO] = None,
        tab_prepare: typing.Optional[TabPrepareDTO] = None,
        tab_wait: typing.Optional[TabWaitDTO] = None,
    ):
        super().__init__()
        self.id = self.get_id()
        self.data = data
        self._timeout = self.MAX_TIMEOUT if timeout is None else timeout
        self.expire_time = time.time() + self._timeout
        self.tab_callback = tab_callback
        self.port = port
        if tab_config is None:
            self.tab_config = ChromeEngine.DEFAULT_TAB_CONFIG
        else:
            self.tab_config = tab_config
        self.tab_prepare = tab_prepare
        self.tab_wait = tab_wait
        self._running_task: typing.Optional[asyncio.Task] = None
        self._tries = 0

    @staticmethod
    def match_url(url: str, pattern_string: str):
        """filter url with fnmatchcase patterns"""
        if not url:
            return False
        patterns = pattern_string.split("|")
        for pattern in patterns:
            if fnmatchcase(url, pattern):
                return True
        return False

    @staticmethod
    def match_request(event: dict, pattern_string: str):
        url = event.get("request", {}).get("url", "")
        return ChromeTask.match_url(url, pattern_string)

    @staticmethod
    def match_response(event: dict, pattern_string: str):
        url = event.get("response", {}).get("url", "")
        return ChromeTask.match_url(url, pattern_string)

    async def _wait_url_request(self, pattern: str, tab: AsyncTab):
        "use tab.wait_request to wait for one of the urls, filter with fnmatchcase"
        return await tab.wait_request(
            filter_function=partial(self.match_request, pattern_string=pattern),
            timeout=self.real_timeout,
        )

    async def _wait_url_response(self, pattern: str, tab: AsyncTab):
        "use tab.wait_response to wait for one of the urls, filter with fnmatchcase"
        return await tab.wait_response(
            filter_function=partial(self.match_response, pattern_string=pattern),
            timeout=self.real_timeout,
        )

    async def _wait_css_callback(self, tab: AsyncTab):
        dto = self.tab_wait
        if not (dto and dto.css):
            return
        includes = dto.includes
        regex = re.compile(dto.regex) if dto.regex else None

        def filter_function(tag: Tag):
            results = [True]
            includes_ok = None
            regex_ok = None
            for text in [tag.outerHTML, tag.textContent]:
                if includes:
                    if not includes_ok:
                        includes_ok = includes in text
                if regex:
                    if not regex_ok:
                        regex_ok = bool(regex.search(text))
            if includes_ok is not None:
                results.append(includes_ok)
            if regex_ok is not None:
                results.append(regex_ok)
            if dto.wait_all_completed:
                return all(results)
            else:
                return any(results)

        return bool(
            await tab.wait_css(
                dto.css,
                filter_function=filter_function,
                max_wait_time=self.real_timeout,
            )
        )

    async def load_start_url(self, url: str, tab: AsyncTab):
        timeout = self.real_timeout
        dto = self.tab_wait
        if not dto:
            return await tab.set_url(url, timeout=timeout)
        else:
            await tab.set_url(url, timeout=0)
            tasks: typing.List[asyncio.Task] = []
            # 1. CSS related
            if dto.css:
                tasks.append(asyncio.create_task(self._wait_css_callback(tab)))
            else:
                if dto.includes:
                    tasks.append(
                        asyncio.create_task(
                            tab.wait_includes(dto.includes, max_wait_time=timeout)
                        )
                    )
                if dto.regex:
                    tasks.append(
                        asyncio.create_task(
                            tab.wait_regex(dto.regex, max_wait_time=timeout)
                        )
                    )
            # 2. CSS non-related
            if dto.js_true:
                tasks.append(
                    asyncio.create_task(
                        tab.wait_js_true(dto.js_true, max_wait_time=timeout)
                    )
                )
            if dto.request_pattern:
                tasks.append(
                    asyncio.create_task(
                        self._wait_url_request(dto.request_pattern, tab)
                    )
                )
            if dto.response_pattern:
                tasks.append(
                    asyncio.create_task(
                        self._wait_url_response(dto.response_pattern, tab)
                    )
                )
            if dto.load:
                tasks.append(asyncio.create_task(tab.wait_loading(dto.load)))
            elif not tasks:
                tasks.append(asyncio.create_task(tab.wait_loading(self.real_timeout)))
            return_when = (
                asyncio.ALL_COMPLETED
                if dto.wait_all_completed
                else asyncio.FIRST_COMPLETED
            )
            await asyncio.wait(tasks, timeout=timeout, return_when=return_when)

    async def run(self, tab: AsyncTab):
        if not self.tab_callback:
            self.set_result(None)
            return
        self._tries += 1
        if self._tries > self.MAX_TRIES:
            logger.info(
                f"[canceled] {self} for tries more than MAX_TRIES: {self._tries} > {self.MAX_TRIES}"
            )
            self.cancel()
            return
        self._running_task = asyncio.create_task(
            ensure_awaitable(self.tab_callback(tab, self.data, self))
        )
        result = None
        try:
            result = await self._running_task
            self.set_result(result)
        except ChromeException as error:
            raise error
        except Exception as error:
            logger.exception(f"{self} catch an error while running task, {error!r}")
            self.set_exception(error)

    def set_result(self, result):
        if self._state == "PENDING":
            super().set_result(result)

    @classmethod
    def get_id(cls):
        cls._ID += 1
        return cls._ID

    @property
    def real_timeout(self) -> float:
        return self.timeout * 0.95

    @property
    def timeout(self) -> float:
        timeout = self.expire_time - time.time()
        if timeout < 0:
            timeout = 0.0
        return timeout

    def cancel_task(self):
        try:
            if self._running_task:
                self._running_task.cancel()
        except AttributeError:
            pass

    def cancel(self, msg=None):
        logger.info(f"[canceled] {self}")
        self.cancel_task()
        super().cancel(msg=msg)

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __str__(self):
        # ChromeTask(<7>, FINISHED)
        return f"{self.__class__.__name__}(<{self.port}>, {self._state}, id={self.id})"

    def __repr__(self) -> str:
        return str(self)


class ChromeWorker:
    DEFAULT_DAEMON_KWARGS: typing.Dict[str, typing.Any] = {}
    MAX_CONCURRENT_TABS = 5
    # auto restart chrome daemon every 8 mins, to avoid zombie processes and memory leakage.
    RESTART_EVERY = 8 * 60
    # --disk-cache-size default cache size 100MB
    DEFAULT_CACHE_SIZE = 100 * 1024**2

    def __init__(
        self,
        port: int,
        max_concurrent_tabs: typing.Optional[int] = None,
        q: typing.Optional[asyncio.PriorityQueue] = None,
        restart_every: typing.Union[float, int, None] = None,
        flatten=None,
        **daemon_kwargs,
    ):
        assert q, "queue should not be null"
        self.port = port
        self.q = q
        self.port_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.restart_every = restart_every or self.RESTART_EVERY
        self.max_concurrent_tabs = max_concurrent_tabs or self.MAX_CONCURRENT_TABS
        self._tab_sem = None
        self._flatten = flatten
        self._shutdown = False
        if self.DEFAULT_CACHE_SIZE:
            _extra = f"--disk-cache-size={self.DEFAULT_CACHE_SIZE}"
            if _extra not in AsyncChromeDaemon.DEFAULT_EXTRA_CONFIG:
                AsyncChromeDaemon.DEFAULT_EXTRA_CONFIG.append(_extra)
        self.daemon_kwargs = daemon_kwargs or deepcopy(self.DEFAULT_DAEMON_KWARGS)
        assert "port" not in self.daemon_kwargs, (
            "invalid key `port` for self.daemon_kwargs"
        )
        self.daemon_task = None
        self.consumers: typing.List[asyncio.Task] = []
        self._running_futures: typing.Set[asyncio.Future] = set()
        self._daemon_start_time = time.time()

    @property
    def todos(self):
        return self.q.qsize()

    @property
    def runnings(self):
        return len(self._running_futures)

    @property
    def is_need_restart(self):
        return self._need_restart.is_set()

    def set_need_restart(self):
        if not self.is_need_restart:
            self._need_restart.set()

    def start_daemon(self):
        self._chrome_daemon_ready = asyncio.Event()
        self._need_restart = asyncio.Event()
        self.daemon_task = self.start_tab_worker()
        self.consumers = [
            asyncio.create_task(self.future_consumer(_))
            for _ in range(self.max_concurrent_tabs)
        ]
        return self.daemon_task

    async def _start_chrome_daemon(self):
        while not self._shutdown:
            self._chrome_daemon_ready.clear()
            self._need_restart.clear()
            self._restart_interval = round(
                self.restart_every + self.get_random_secs(), 3
            )
            self._will_restart_peacefully = False
            async with AsyncChromeDaemon(
                port=self.port, **self.daemon_kwargs
            ) as chrome_daemon:
                self._daemon_start_time = time.time()
                self.chrome_daemon = chrome_daemon
                for _ in range(10):
                    if await chrome_daemon.connection_ok:
                        self._chrome_daemon_ready.set()
                        break
                    await asyncio.sleep(0.5)
                else:
                    logger.info(f"[error] {self} launch failed.")
                    continue
                logger.info(f"[online] {self} is online.")
                while 1:
                    await self._need_restart.wait()
                    self._chrome_daemon_ready.clear()
                    # waiting for all _running_futures done.
                    if not self._will_restart_peacefully:
                        break
                    elif self._will_restart_peacefully and not self._running_futures:
                        msg = f"restarting for interval {self._restart_interval}. ({self})"
                        logger.info(msg)
                        break
                logger.info(f"[offline] {self} is offline.")

    async def prepare_tab(self, tab: AsyncTab, dto: TabPrepareDTO):
        if dto.cookies:
            for name, value in dto.cookies.items():
                # may need set url param for cross-site cookies TODO
                await tab.set_cookie(name=name, value=value)
        if dto.ua:
            await tab.set_ua(dto.ua)
        if dto.headers:
            await tab.set_headers(dto.headers)
        if dto.block_urls:
            await tab.setBlockedURLs(dto.block_urls.split("|"))
        if dto.add_js_onload:
            await tab.add_js_onload(dto.add_js_onload)

    async def future_consumer(self, index=None):
        while not self._shutdown:
            run_too_long = (
                time.time() - self._daemon_start_time > self._restart_interval
            )
            if run_too_long and not self.is_need_restart:
                # stop consuming new futures
                self._chrome_daemon_ready.clear()
                for f in self._running_futures:
                    await f
                self._will_restart_peacefully = True
                # time to restart
                self._need_restart.set()
            try:
                # try self port queue at first
                future = typing.cast(ChromeTask, self.port_queue.get_nowait())
            except asyncio.QueueEmpty:
                future = await self.q.get()
            logger.info(f"{self} get a new task {future}.")
            if future.data is ChromeTask.STOP_SIG:
                if future.port:
                    await self.port_queue.put(future)
                else:
                    await self.q.put(future)
                break
            if future.done() or future.expire_time < time.time():
                # overdue task, skip
                continue
            await self._chrome_daemon_ready.wait()
            if await self.chrome_daemon._check_chrome_connection():
                # incognito mode
                _kwargs = asdict(future.tab_config) if future.tab_config else {}
                async with self.chrome_daemon.incognito_tab(**_kwargs) as tab:
                    if future.tab_prepare:
                        await self.prepare_tab(tab, future.tab_prepare)
                    if isinstance(future.data, _TabWorker):
                        await self.handle_tab_worker_future(tab, future)
                    else:
                        await self.handle_default_future(tab, future)
            else:
                self._chrome_daemon_ready.clear()
                self.set_need_restart()
                if future.port:
                    await self.port_queue.put(future)
                else:
                    await self.q.put(future)
        return f"{self} future_consumer[{index}] done."

    async def handle_tab_worker_future(self, tab, future: ChromeTask):
        try:
            tab_worker: _TabWorker = future.data
            tab_worker.tab_future.set_result(tab)
            return await asyncio.wait_for(
                tab_worker._done.wait(), timeout=future.timeout
            )
        except (asyncio.CancelledError, asyncio.TimeoutError):
            return
        except ChromeException as error:
            if not self._shutdown:
                logger.error(f"{self} restarting for error {error!r}")
                self.set_need_restart()
        finally:
            if not future.done():
                future.cancel()
            logger.info(f"[finished]({self.todos}) {future}")
            del future

    async def handle_default_future(self, tab, future):
        try:
            self._running_futures.add(future)
            await future.run(tab)
        except ChromeEngine.ERRORS_NOT_HANDLED as error:
            raise error
        except asyncio.CancelledError:
            pass
        except ChromeException as error:
            if not self._shutdown:
                logger.error(f"{self} restarting for error {error!r}")
                self.set_need_restart()
        except Exception as error:
            # other errors may give a retry
            logger.error(f"{self} catch an error {error!r} for {future}")
        finally:
            self._running_futures.discard(future)
            if not future.done():
                # retry
                future.cancel_task()
                await self.q.put(future)

    def start_tab_worker(self):
        return asyncio.create_task(self._start_chrome_daemon())

    async def shutdown(self):
        if self._shutdown:
            return
        self._shutdown = True
        self._need_restart.set()
        if self.daemon_task:
            await self.daemon_task
        for task in self.consumers:
            task.cancel()
        await asyncio.sleep(0.01)

    def get_random_secs(self, start=0, end=5):
        return random.choice(range(start * 1000, end * 1000)) / 1000

    def __str__(self):
        return f"{self.__class__.__name__}(<{self.port}>, {self.runnings}/{self.max_concurrent_tabs}, {self.todos} todos)"

    def __repr__(self) -> str:
        return str(self)


class ChromeEngine:
    START_PORT = 9345
    DEFAULT_WORKERS_AMOUNT = 1
    ERRORS_NOT_HANDLED = (KeyboardInterrupt,)
    SHORTEN_DATA_LENGTH = 150
    FLATTEN = True
    # Use incognico mode by default, or you can se ChromeEngine.DEFAULT_TAB_CONFIG = None to use normal mode
    DEFAULT_TAB_CONFIG: typing.Optional[TabConfigDTO] = None

    def __init__(
        self,
        workers_amount: typing.Optional[int] = None,
        max_concurrent_tabs=None,
        start_port: typing.Optional[int] = None,
        **daemon_kwargs,
    ):
        self._q: typing.Union[asyncio.PriorityQueue, None] = None
        self._shutdown = False
        # max tab currency num
        self.workers: typing.Dict[int, ChromeWorker] = {}
        self.workers_amount = workers_amount or self.DEFAULT_WORKERS_AMOUNT
        self.max_concurrent_tabs = max_concurrent_tabs
        self.start_port = daemon_kwargs.pop("port", start_port) or self.START_PORT
        self.daemon_kwargs = daemon_kwargs

    @property
    def todos(self):
        return self.q.qsize()

    @property
    def q(self) -> asyncio.PriorityQueue:
        if not self._q:
            self._q = asyncio.PriorityQueue()
        return self._q

    def _add_default_workers(self):
        for offset in range(self.workers_amount):
            port = self.start_port + offset
            worker = ChromeWorker(
                port=port,
                max_concurrent_tabs=self.max_concurrent_tabs,
                q=self.q,
                flatten=self.FLATTEN,
                **self.daemon_kwargs,
            )
            self.workers[port] = worker

    async def start_workers(self):
        if not self.workers:
            self._add_default_workers()
        for worker in self.workers.values():
            worker.start_daemon()
        return self

    async def start(self):
        return await self.start_workers()

    def shorten_data(self, data):
        if isinstance(data, dict):
            repr_data = repr({k: self.shorten_data(v) for k, v in data.items()})
            return repr_data
        else:
            repr_data = str(data)
            return f"{repr_data[: self.SHORTEN_DATA_LENGTH]}{'...' if len(repr_data) > self.SHORTEN_DATA_LENGTH else ''}"

    def release(self):
        while not self.q.empty():
            try:
                future = self.q.get_nowait()
                if future.data is not ChromeTask.STOP_SIG and not future.done():
                    future.cancel()
                del future
            except asyncio.QueueEmpty:
                break

    async def shutdown(self):
        if self._shutdown:
            return
        for _ in self.workers:
            await self.q.put(ChromeTask(ChromeTask.STOP_SIG, None))
        self._shutdown = True
        self.release()
        for worker in self.workers.values():
            await worker.shutdown()
        return self

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        return await self.shutdown()

    async def do(
        self,
        data: typing.Any,
        tab_callback: typing.Optional[typing.Callable] = None,
        timeout: typing.Optional[float] = None,
        port: typing.Optional[int] = None,
        tab_config: typing.Optional[TabConfigDTO] = None,
        tab_prepare: typing.Optional[TabPrepareDTO] = None,
        tab_wait: typing.Optional[TabWaitDTO] = None,
    ):
        if self._shutdown:
            raise RuntimeError(f"{self.__class__.__name__} has been shutdown.")
        future = ChromeTask(
            data,
            tab_callback,
            timeout=timeout,
            port=port,
            tab_config=tab_config,
            tab_prepare=tab_prepare,
            tab_wait=tab_wait,
        )
        if port:
            await self.workers[port].port_queue.put(future)
        else:
            await self.q.put(future)
        logger.info(
            f"[TODO]({self.todos}) {future}, timeout={timeout}, data={self.shorten_data(data)}, tab_config={tab_config}, tab_prepare={tab_prepare}, tab_wait={tab_wait}"
        )
        try:
            return await asyncio.wait_for(future, timeout=future.timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            logger.info(f"[DONE]({self.todos}) {future}")
            del future

    async def screenshot(
        self,
        dto: ScreenshotDTO,
        timeout: typing.Optional[float] = None,
        tab_config: typing.Optional[TabConfigDTO] = None,
        tab_prepare: typing.Optional[TabPrepareDTO] = None,
        tab_wait: typing.Optional[TabWaitDTO] = None,
    ) -> bytes:
        image = typing.cast(
            bytes,
            await self.do(
                data=dto,
                tab_callback=ScreenshotCallback(),
                timeout=timeout,
                tab_config=tab_config,
                tab_prepare=tab_prepare,
                tab_wait=tab_wait,
            ),
        )
        return image

    async def download(
        self,
        dto: DownloadDTO,
        timeout: typing.Optional[float] = None,
        tab_config: typing.Optional[TabConfigDTO] = None,
        tab_prepare: typing.Optional[TabPrepareDTO] = None,
        tab_wait: typing.Optional[TabWaitDTO] = None,
    ) -> DownloadResult:
        result = typing.cast(
            DownloadResult,
            await self.do(
                data=dto,
                tab_callback=DownloadCallback(),
                timeout=timeout,
                tab_config=tab_config,
                tab_prepare=tab_prepare,
                tab_wait=tab_wait,
            ),
        )
        return result

    async def js(
        self,
        dto: JsDTO,
        timeout: typing.Optional[float] = None,
        tab_config: typing.Optional[TabConfigDTO] = None,
        tab_prepare: typing.Optional[TabPrepareDTO] = None,
        tab_wait: typing.Optional[TabWaitDTO] = None,
    ) -> dict:
        return typing.cast(
            dict,
            await self.do(
                data=dto,
                tab_callback=JSCallback(),
                timeout=timeout,
                tab_config=tab_config,
                tab_prepare=tab_prepare,
                tab_wait=tab_wait,
            ),
        )


class _TabWorker:
    """
    Used with `async with` context for ChromeEngine.
    """

    def __init__(self):
        pass

    async def __aenter__(self) -> AsyncTab:
        self._done = asyncio.Event()
        self.tab_future: typing.Any = asyncio.Future()
        # waiting for a tab
        await self.tab_future
        return self.tab_future.result()

    async def __aexit__(self, *_):
        self._done.set()


class ScreenshotCallback(CallbackProtocol):
    @staticmethod
    async def __call__(tab: AsyncTab, data: ScreenshotDTO, task: ChromeTask) -> bytes:
        await task.load_start_url(data.url, tab)
        timeout = task.real_timeout
        result = await asyncio.wait_for(
            tab.screenshot_element(
                cssselector=data.cssselector,
                scale=data.scale,
                format=data.format,
                quality=data.quality,
                fromSurface=data.fromSurface,
                save_path=None,
                captureBeyondViewport=data.captureBeyondViewport,
            ),
            timeout=timeout,
        )
        if result:
            return b64decode(result)
        else:
            return b""


class DownloadCallback(CallbackProtocol):
    @staticmethod
    async def __call__(
        tab: AsyncTab, data: DownloadDTO, task: ChromeTask
    ) -> DownloadResult:
        result = DownloadResult(url=data.url)
        await task.load_start_url(data.url, tab)
        if data.cssselector:
            tags: typing.Any = await tab.querySelectorAll(data.cssselector)
            result.tags = [tag.outerHTML for tag in tags]
        else:
            result.html = (await tab.current_html) or ""
        try:
            temp = typing.cast(
                list,
                await tab.get_value(
                    r'[document.title || document.body.textContent.trim().replace(/\s+/g, " ").slice(0,100), document.charset]',
                    jsonify=True,
                ),
            )
            if temp:
                result.title, result.encoding = temp
        except Exception:
            pass
        result.current_url = await tab.current_url
        return result


class JSCallback(CallbackProtocol):
    @staticmethod
    async def __call__(tab: AsyncTab, data: JsDTO, task: ChromeTask) -> dict:
        await task.load_start_url(data.url, tab)
        result = await tab.js(javascript=data.js, value_path=data.value_path)
        return typing.cast(dict, result)
