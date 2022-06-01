import asyncio
import random
import time
import typing
from base64 import b64decode
from copy import deepcopy

from . import AsyncChromeDaemon, AsyncTab
from .base import ensure_awaitable
from .exceptions import ChromeException
from .logs import logger


class ChromeTask(asyncio.Future):
    """ExpireFuture"""
    _ID = 0
    MAX_TIMEOUT = 60 * 5
    MAX_TRIES = 5
    EXEC_GLOBALS: typing.Dict[str, typing.Any] = {}
    STOP_SIG = object()

    def __init__(self,
                 data,
                 tab_callback: typing.Callable = None,
                 timeout=None,
                 tab_index=None,
                 port=None,
                 incognito_args=None):
        super().__init__()
        self.id = self.get_id()
        self.data = data
        self.tab_index = tab_index
        self._timeout = self.MAX_TIMEOUT if timeout is None else timeout
        self.expire_time = time.time() + self._timeout
        self.tab_callback = self.ensure_tab_callback(tab_callback)
        self.port = port
        if incognito_args is None:
            self.incognito_args: dict = ChromeEngine.DEFAULT_INCOGNITO_ARGS
        else:
            self.incognito_args: dict = incognito_args
        self._running_task: asyncio.Task = None
        self._tries = 0

    @staticmethod
    async def _default_tab_callback(self: 'ChromeTask', tab: AsyncTab,
                                    data: typing.Any, timeout: float):
        return

    def ensure_tab_callback(self, tab_callback):
        if tab_callback and isinstance(tab_callback, str):
            exec_locals = {'tab_callback': None}
            exec(tab_callback, self.EXEC_GLOBALS, exec_locals)
            tab_callback = exec_locals['tab_callback']
            if not tab_callback:
                raise RuntimeError(
                    'tab_callback source code should has function like `tab_callback(self: "ChromeTask", tab: AsyncTab, data: typing.Any, timeout: float)`'
                )
        return tab_callback or self._default_tab_callback

    async def run(self, tab: AsyncTab):
        self._tries += 1
        if self._tries > self.MAX_TRIES:
            logger.info(
                f'[canceled] {self} for tries more than MAX_TRIES: {self._tries} > {self.MAX_TRIES}'
            )
            return self.cancel()
        self._running_task = asyncio.create_task(
            ensure_awaitable(
                self.tab_callback(self, tab, self.data, timeout=self.timeout)))
        result = None
        try:
            result = await self._running_task
            self.set_result(result)
        except ChromeException as error:
            raise error
        except Exception as error:
            logger.error(f'{self} catch an error while running task, {error!r}')
            self.set_result(result)

    def set_result(self, result):
        if self._state == 'PENDING':
            super().set_result(result)

    @classmethod
    def get_id(cls):
        cls._ID += 1
        return cls._ID

    @property
    def timeout(self):
        timeout = self.expire_time - time.time()
        if timeout < 0:
            timeout = 0
        return timeout

    def cancel_task(self):
        try:
            self._running_task.cancel()
        except AttributeError:
            pass

    def cancel(self):
        logger.info(f'[canceled] {self}')
        self.cancel_task()
        super().cancel()

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __str__(self):
        # ChromeTask(<7>, FINISHED)
        return f'{self.__class__.__name__}(<{self.port}>, {self._state}, id={self.id}, tab={self.tab_index})'

    def __repr__(self) -> str:
        return str(self)


class ChromeWorker:
    DEFAULT_DAEMON_KWARGS: typing.Dict[str, typing.Any] = {}
    MAX_CONCURRENT_TABS = 5
    # auto restart chrome daemon every 8 mins, to avoid zombie processes and memory leakage.
    RESTART_EVERY = 8 * 60
    # --disk-cache-size default cache size 100MB
    DEFAULT_CACHE_SIZE = 100 * 1024**2

    def __init__(self,
                 port=None,
                 max_concurrent_tabs: int = None,
                 q: asyncio.PriorityQueue = None,
                 restart_every: typing.Union[float, int] = None,
                 flatten=None,
                 **daemon_kwargs):
        assert q, 'queue should not be null'
        self.port = port
        self.q = q
        self.port_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.restart_every = restart_every or self.RESTART_EVERY
        self.max_concurrent_tabs = max_concurrent_tabs or self.MAX_CONCURRENT_TABS
        self._tab_sem = None
        self._flatten = flatten
        self._shutdown = False
        if self.DEFAULT_CACHE_SIZE:
            _extra = f'--disk-cache-size={self.DEFAULT_CACHE_SIZE}'
            if _extra not in AsyncChromeDaemon.DEFAULT_EXTRA_CONFIG:
                AsyncChromeDaemon.DEFAULT_EXTRA_CONFIG.append(_extra)
        self.daemon_kwargs = daemon_kwargs or deepcopy(
            self.DEFAULT_DAEMON_KWARGS)
        assert 'port' not in self.daemon_kwargs, 'invalid key `port` for self.daemon_kwargs'
        self.daemon_task = None
        self.consumers: typing.List[asyncio.Task] = []
        self._running_futures: typing.Set[int] = set()
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
                self.restart_every + self.get_random_secs(), 3)
            self._will_restart_peacefully = False
            async with AsyncChromeDaemon(port=self.port,
                                         **self.daemon_kwargs) as chrome_daemon:
                self._daemon_start_time = time.time()
                self.chrome_daemon = chrome_daemon
                for _ in range(10):
                    if await chrome_daemon.connection_ok:
                        self._chrome_daemon_ready.set()
                        break
                    await asyncio.sleep(0.5)
                else:
                    logger.info(f'[error] {self} launch failed.')
                    continue
                logger.info(f'[online] {self} is online.')
                while 1:
                    await self._need_restart.wait()
                    self._chrome_daemon_ready.clear()
                    # waiting for all _running_futures done.
                    if not self._will_restart_peacefully:
                        break
                    elif self._will_restart_peacefully and not self._running_futures:
                        msg = f'restarting for interval {self._restart_interval}. ({self})'
                        logger.info(msg)
                        break
                logger.info(f'[offline] {self} is offline.')

    async def future_consumer(self, index=None):
        while not self._shutdown:
            run_too_long = time.time(
            ) - self._daemon_start_time > self._restart_interval
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
                future: ChromeTask = self.port_queue.get_nowait()
            except asyncio.QueueEmpty:
                future: ChromeTask = await self.q.get()
            logger.info(f'{self} get a new task {future}.')
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
                if isinstance(future.incognito_args, dict):
                    # incognito mode
                    async with self.chrome_daemon.incognito_tab(
                            **future.incognito_args) as tab:
                        if isinstance(future.data, _TabWorker):
                            await self.handle_tab_worker_future(tab, future)
                        else:
                            await self.handle_default_future(tab, future)
                else:
                    # should not auto_close for int index (existing tab).
                    auto_close = not isinstance(future.tab_index, int)
                    async with self.chrome_daemon.connect_tab(
                            index=future.tab_index,
                            auto_close=auto_close,
                            flatten=self._flatten) as tab:
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
        return f'{self} future_consumer[{index}] done.'

    async def handle_tab_worker_future(self, tab, future):
        try:
            tab_worker: _TabWorker = future.data
            tab_worker.tab_future.set_result(tab)
            return await asyncio.wait_for(tab_worker._done.wait(),
                                          timeout=future.timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            return
        except ChromeException as error:
            if not self._shutdown:
                logger.error(f'{self} restarting for error {error!r}')
                self.set_need_restart()
        finally:
            logger.info(f'[finished]({self.todos}) {future}')
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
                logger.error(f'{self} restarting for error {error!r}')
                self.set_need_restart()
        except Exception as error:
            # other errors may give a retry
            logger.error(f'{self} catch an error {error!r} for {future}')
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
        await self.daemon_task
        for task in self.consumers:
            task.cancel()

    def get_random_secs(self, start=0, end=5):
        return random.choice(range(start * 1000, end * 1000)) / 1000

    def __str__(self):
        return f'{self.__class__.__name__}(<{self.port}>, {self.runnings}/{self.max_concurrent_tabs}, {self.todos} todos)'

    def __repr__(self) -> str:
        return str(self)


class ChromeEngine:
    START_PORT = 9345
    DEFAULT_WORKERS_AMOUNT = 1
    ERRORS_NOT_HANDLED = (KeyboardInterrupt,)
    SHORTEN_DATA_LENGTH = 150
    FLATTEN = True
    # Use incognico mode by default, or you can se ChromeEngine.DEFAULT_INCOGNITO_ARGS = None to use normal mode
    DEFAULT_INCOGNITO_ARGS = {}

    def __init__(self,
                 workers_amount: int = None,
                 max_concurrent_tabs=None,
                 **daemon_kwargs):
        self._q: typing.Union[asyncio.PriorityQueue, asyncio.Queue] = None
        self._shutdown = False
        # max tab currency num
        self.workers: typing.Dict[int, ChromeWorker] = {}
        self.workers_amount = workers_amount or self.DEFAULT_WORKERS_AMOUNT
        self.max_concurrent_tabs = max_concurrent_tabs
        self.start_port = daemon_kwargs.pop('port', None) or self.START_PORT
        self.daemon_kwargs = daemon_kwargs

    @property
    def todos(self):
        return self.q.qsize()

    @property
    def q(self):
        if not self._q:
            self._q = asyncio.PriorityQueue()
        return self._q

    def _add_default_workers(self):
        for offset in range(self.workers_amount):
            port = self.start_port + offset
            worker = ChromeWorker(port=port,
                                  max_concurrent_tabs=self.max_concurrent_tabs,
                                  q=self.q,
                                  flatten=self.FLATTEN,
                                  **self.daemon_kwargs)
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
        repr_data = repr(data)
        return f'{repr_data[:self.SHORTEN_DATA_LENGTH]}{"..." if len(repr_data)>self.SHORTEN_DATA_LENGTH else ""}'

    async def do(self,
                 data,
                 tab_callback,
                 timeout: float = None,
                 tab_index=None,
                 port=None,
                 incognito_args: dict = None):
        if self._shutdown:
            raise RuntimeError(f'{self.__class__.__name__} has been shutdown.')
        future = ChromeTask(data,
                            tab_callback,
                            timeout=timeout,
                            tab_index=tab_index,
                            port=port,
                            incognito_args=incognito_args)
        if port:
            await self.workers[port].port_queue.put(future)
        else:
            await self.q.put(future)
        logger.info(
            f'[enqueue]({self.todos}) {future}, timeout={timeout}, data={self.shorten_data(data)}'
        )
        try:
            return await asyncio.wait_for(future, timeout=future.timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            logger.info(f'[finished]({self.todos}) {future}')
            del future

    async def shutdown(self):
        if self._shutdown:
            return
        for _ in self.workers:
            await self.q.put(ChromeTask(ChromeTask.STOP_SIG, 0))
        self._shutdown = True
        self.release()
        for worker in self.workers.values():
            await worker.shutdown()
        return self

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        return await self.shutdown()

    def release(self):
        while not self.q.empty():
            try:
                future = self.q.get_nowait()
                if future.data is not ChromeTask.STOP_SIG and not future.done():
                    future.cancel()
                del future
            except asyncio.QueueEmpty:
                break

    async def screenshot(
            self,
            url: str,
            cssselector: str = None,
            scale=1,
            format: str = 'png',
            quality: int = 100,
            fromSurface: bool = True,
            save_path=None,
            timeout=None,
            as_base64=True,
            captureBeyondViewport=False) -> typing.Union[str, bytes]:
        data = dict(url=url,
                    cssselector=cssselector,
                    scale=scale,
                    format=format,
                    quality=quality,
                    fromSurface=fromSurface,
                    save_path=save_path,
                    captureBeyondViewport=bool(captureBeyondViewport))
        image = await self.do(data=data,
                              tab_callback=CommonUtils.screenshot,
                              timeout=timeout,
                              tab_index=None)
        if as_base64 or not image:
            return image
        else:
            return b64decode(image)

    async def download(self,
                       url: str,
                       cssselector: str = None,
                       wait_tag: str = None,
                       timeout=None) -> dict:

        data = dict(url=url, cssselector=cssselector, wait_tag=wait_tag)
        return await self.do(data=data,
                             tab_callback=CommonUtils.download,
                             timeout=timeout,
                             tab_index=None)

    async def preview(self,
                      url: str,
                      wait_tag: str = None,
                      timeout=None) -> bytes:
        data = await self.download(url, wait_tag=wait_tag, timeout=timeout)
        if data:
            return data['html'].encode(data.get('encoding') or 'utf-8')
        else:
            return b''

    async def js(self,
                 url: str,
                 js: str,
                 value_path='result.result',
                 wait_tag: str = None,
                 timeout=None) -> bytes:
        data = dict(url=url, js=js, value_path=value_path, wait_tag=wait_tag)
        return await self.do(data=data,
                             tab_callback=CommonUtils.js,
                             timeout=timeout,
                             tab_index=None)

    def connect_tab(self,
                    tab_index=None,
                    timeout: float = None,
                    port: int = None):
        data = _TabWorker()
        future = ChromeTask(data,
                            timeout=timeout,
                            tab_index=tab_index,
                            port=port)
        logger.info(
            f'[enqueue]({self.todos}) {future}, timeout={timeout}, data={self.shorten_data(data)}'
        )
        if port:
            self.workers[port].port_queue.put_nowait(future)
        else:
            self.q.put_nowait(future)
        return data


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


class CommonUtils:
    """Some frequently-used callback functions."""

    async def screenshot(self, tab: AsyncTab, data, timeout):
        await tab.set_url(data.pop('url'), timeout=timeout)
        return await tab.screenshot_element(timeout=timeout, **data)

    async def download(self, tab: AsyncTab, data, timeout):
        start_time = time.time()
        result = {'url': data['url']}
        await tab.set_url(data['url'], timeout=timeout)
        if data['wait_tag']:
            timeout = timeout - (time.time() - start_time)
            if timeout > 0:
                await tab.wait_tag(data['wait_tag'], max_wait_time=timeout)
        if data['cssselector']:
            result['html'] = None
            tags = await tab.querySelectorAll(data['cssselector'])
            result['tags'] = [tag.outerHTML for tag in tags]
        else:
            result['html'] = await tab.current_html
            result['tags'] = []
        title, encoding = await tab.get_value(
            r'[document.title || document.body.textContent.trim().replace(/\s+/g, " ").slice(0,50), document.charset]',
            jsonify=True)
        result['title'] = title
        result['encoding'] = encoding
        return result

    async def js(self, tab: AsyncTab, data, timeout):
        await tab.set_url(data['url'], timeout=timeout)
        return await tab.js(javascript=data['js'],
                            value_path=data['value_path'])
