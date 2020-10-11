import asyncio
import random
import time
from tkinter import EXCEPTION
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
    MAX_TIMEOUT = 60
    MAX_TRIES = 5
    EXEC_GLOBALS: typing.Dict[str, typing.Any] = {}
    STOP_SIG = object()

    def __init__(self,
                 data,
                 tab_callback: typing.Callable = None,
                 timeout=None,
                 tab_index=None):
        super().__init__()
        self.id = self.get_id()
        self.data = data
        self.tab_index = tab_index
        self._timeout = self.MAX_TIMEOUT if timeout is None else timeout
        self.expire_time = time.time() + self._timeout
        self.tab_callback = self.ensure_tab_callback(tab_callback)
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
        except Exception as error:
            logger.error(f'{self} catch an error while running task, {error!r}')
        finally:
            if self._state == 'PENDING':
                self.set_result(result)

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
        return f'{self.__class__.__name__}(<{self.id}>, {self._state})'

    def __repr__(self) -> str:
        return str(self)


class ChromeWorker:
    DEFAULT_DAEMON_KWARGS: typing.Dict[str, typing.Any] = {}
    MAX_CONCURRENT_TABS = 5
    # auto restart chrome daemon every 8 mins, to avoid zombie processes and memory leakage.
    RESTART_EVERY = 8 * 60

    def __init__(self,
                 port=None,
                 max_concurrent_tabs: int = None,
                 q: asyncio.PriorityQueue = None,
                 restart_every: typing.Union[float, int] = None,
                 **daemon_kwargs):
        assert q, 'queue should not be null'
        self.port = port
        self.q = q
        self.restart_every = restart_every or self.RESTART_EVERY
        self.max_concurrent_tabs = max_concurrent_tabs or self.MAX_CONCURRENT_TABS
        self._tab_sem = None
        self._shutdown = False
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

    def start_daemon(self):
        self._chrome_daemon_ready = asyncio.Event()
        self._need_restart = asyncio.Event()
        self.daemon_task = asyncio.create_task(self._start_chrome_daemon())
        self.consumers = [
            asyncio.create_task(self.future_consumer(_))
            for _ in range(self.max_concurrent_tabs)
        ]
        return self.daemon_task

    async def _start_chrome_daemon(self):
        while not self._shutdown:
            self._restart_interval = round(
                self.restart_every + self.get_random_secs(), 3)
            self._will_restart_peacefully = False
            self._chrome_daemon_ready.clear()
            self._need_restart.clear()
            async with AsyncChromeDaemon(port=self.port,
                                         **self.daemon_kwargs) as chrome_daemon:
                self._daemon_start_time = time.time()
                self.chrome_daemon = chrome_daemon
                self._chrome_daemon_ready.set()
                logger.info(f'[online] {self} is online.')
                while 1:
                    await self._need_restart.wait()
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
            if time.time() - self._daemon_start_time > self._restart_interval:
                # stop consuming new futures
                self._chrome_daemon_ready.clear()
                for f in self._running_futures:
                    await f
                self._will_restart_peacefully = True
                # time to restart
                self._need_restart.set()
            await self._chrome_daemon_ready.wait()
            future: ChromeTask = await self.q.get()
            if future.data is ChromeTask.STOP_SIG:
                await self.q.put(future)
                break
            if future.done() or future.expire_time < time.time():
                # overdue task, skip
                continue
            if await self.chrome_daemon._check_chrome_connection():
                async with self.chrome_daemon.connect_tab(
                        index=future.tab_index, auto_close=True) as tab:
                    try:
                        self._running_futures.add(future)
                        await future.run(tab)
                        continue
                    except ChromeEngine.ERRORS_NOT_HANDLED as error:
                        raise error
                    except asyncio.CancelledError:
                        continue
                    except ChromeException as error:
                        logger.error(f'{self} restarting for error {error!r}')
                        if not self._need_restart.is_set():
                            self._need_restart.set()
                    except Exception as error:
                        logger.error(
                            f'{self} catch an error {error!r} for {future}')
                    finally:
                        self._running_futures.discard(future)
                        if not future.done():
                            # retry
                            future.cancel_task()
                            await self.q.put(future)
            else:
                if not self._need_restart.is_set():
                    self._need_restart.set()
                await self.q.put(future)
        return f'{self} future_consumer[{index}] done.'

    def start_tab_worker(self):
        asyncio.create_task(self._start_chrome_daemon())

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
    DEFAULT_WORKERS_AMOUNT = 2
    ERRORS_NOT_HANDLED = (KeyboardInterrupt,)
    SHORTEN_DATA_LENGTH = 150

    def __init__(self,
                 workers_amount: int = None,
                 max_concurrent_tabs=None,
                 **daemon_kwargs):
        self._q: typing.Union[asyncio.PriorityQueue, asyncio.Queue] = None
        self._shutdown = False
        # max tab currency num
        self.workers: typing.List[ChromeWorker] = []
        self.workers_amount = workers_amount or self.DEFAULT_WORKERS_AMOUNT
        self.max_concurrent_tabs = max_concurrent_tabs
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
            port = self.START_PORT + offset
            worker = ChromeWorker(port=port,
                                  max_concurrent_tabs=self.max_concurrent_tabs,
                                  q=self.q,
                                  **self.daemon_kwargs)
            self.workers.append(worker)

    async def start_workers(self):
        if not self.workers:
            self._add_default_workers()
        for worker in self.workers:
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
                 tab_index=None):
        if self._shutdown:
            raise RuntimeError(f'{self.__class__.__name__} has been shutdown.')
        future = ChromeTask(data,
                            tab_callback,
                            timeout=timeout,
                            tab_index=tab_index)
        logger.info(
            f'[enqueue]({self.todos}) {future} with timeout={timeout}, tab_index={tab_index}, data={self.shorten_data(data)}'
        )
        await self.q.put(future)
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
        for worker in self.workers:
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

    async def screenshot(self,
                         url: str,
                         cssselector: str = None,
                         scale=1,
                         format: str = 'png',
                         quality: int = 100,
                         fromSurface: bool = True,
                         save_path=None,
                         timeout=None,
                         as_base64=True) -> typing.Union[str, bytes]:
        data = dict(url=url,
                    cssselector=cssselector,
                    scale=scale,
                    format=format,
                    quality=quality,
                    fromSurface=fromSurface,
                    save_path=save_path)
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
