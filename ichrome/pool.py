import asyncio
import random
import time
import typing
from copy import deepcopy
from . import AsyncChromeDaemon, AsyncTab
from .exceptions import ChromeException
from .logs import logger
from .base import ensure_awaitable


class ExpireFuture(asyncio.Future):
    _ID = 0
    MAX_TIMEOUT = 60
    MAX_TRIES = 5
    EXEC_GLOBALS: typing.Dict[str, typing.Any] = {}
    EXEC_LOCALS: typing.Dict[str, typing.Any] = {}

    def __init__(self,
                 data,
                 tab_callback: typing.Callable = None,
                 timeout=None):
        super().__init__()
        self.id = self.get_id()
        self.data = data
        self.timeout = self.MAX_TIMEOUT if timeout is None else timeout
        self.expire_time = time.time() + self.timeout
        self.tab_callback = self.ensure_function(tab_callback)
        self._running_task: asyncio.Task = None
        self._tries = 0

    def ensure_function(self, tab_callback):
        if tab_callback and isinstance(tab_callback, str):
            tab_callback = exec(tab_callback, self.EXEC_GLOBALS,
                                self.EXEC_LOCALS)
        return tab_callback or self._default_tab_callback

    @classmethod
    def get_id(cls):
        cls._ID += 1
        return cls._ID

    @property
    def real_timeout(self):
        timeout = self.expire_time - time.time()
        if timeout < 0:
            timeout = 0
        return timeout

    def cancel(self):
        try:
            self._running_task.cancel()
        except AttributeError:
            pass
        super().cancel()

    async def _default_tab_callback(self, tab: AsyncTab, data: typing.Any,
                                    timeout: float):
        return

    async def run(self, tab: AsyncTab):
        self._tries += 1
        if self._tries > self.MAX_TRIES:
            return self.cancel()
        self._running_task = asyncio.create_task(
            ensure_awaitable(
                self.tab_callback(tab, self.data, timeout=self.real_timeout)))
        result = await self._running_task
        if self._state == 'PENDING':
            self.set_result(result)

    @property
    def timeleft(self):
        return time.time() - self.expire_time

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __str__(self):
        return f'ChromeTask<{self.id}>'

    def __repr__(self) -> str:
        return str(self)

    def __del__(self):
        if not self.done():
            self.cancel()
        super().__del__()


class ChromeWorker:
    STOP_SIG = object()
    DEFAULT_DAEMON_KWARGS: typing.Dict[str, typing.Any] = {}
    MAX_CONCURRENT_TABS = 5
    # auto restart chrome daemon every 8 mins, to avoid zombie processes or memory leakage.
    RESTART_INTERVAL = 8 * 60

    def __init__(self,
                 port=None,
                 max_concurrent_tabs: int = None,
                 q: asyncio.PriorityQueue = None,
                 **daemon_kwargs):
        assert q, 'queue should not be null'
        self.port = port
        self.q = q
        self.max_concurrent_tabs = max_concurrent_tabs or self.MAX_CONCURRENT_TABS
        self._tab_sem = None
        self._shutdown = False
        self.daemon_kwargs = daemon_kwargs or deepcopy(
            self.DEFAULT_DAEMON_KWARGS)
        assert 'port' not in self.daemon_kwargs, 'invalid key `port` for self.daemon_kwargs'
        self.daemon_task = None
        self.consumers: typing.List[asyncio.Task] = []
        self._running_tabs: typing.Set[int] = set()

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
            self._chrome_daemon_ready.clear()
            self._need_restart.clear()
            async with AsyncChromeDaemon(port=self.port,
                                         **self.daemon_kwargs) as chrome_daemon:
                self.chrome_daemon = chrome_daemon
                self._chrome_daemon_ready.set()
                logger.info(f'{self} is online.')
                await self._need_restart.wait()
                logger.info(f'{self} is offline.')

    async def future_consumer(self, index=None):
        while not self._shutdown:
            self._running_tabs.discard(index)
            await self._chrome_daemon_ready.wait()
            future: ExpireFuture = await self.q.get()
            if future.data is self.STOP_SIG:
                await self.q.put(future)
                break
            if future.expire_time < time.time():
                # overdue task, skip
                continue
            self._running_tabs.add(index)
            if await self.chrome_daemon._check_chrome_connection():
                async with self.chrome_daemon.connect_tab(
                        index=None, auto_close=True) as tab:
                    try:
                        await future.run(tab)
                        continue
                    except ChromeEngine.ERRORS_NOT_HANDLED as error:
                        raise error
                    except ChromeException as error:
                        logger.error(f'{self} catch an error {error!r}')
                        self._need_restart.set()
                    except Exception as error:
                        logger.error(
                            f'{self} catch an error {error!r} for {future}')
            if not self._shutdown:
                await self.q.put(future)
        self._running_tabs.discard(index)
        return f'{self} {index} future_consumer done.'

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
        return f'ChromeWorker<{self.port}>({len(self._running_tabs)}/{self.max_concurrent_tabs})'

    def __repr__(self) -> str:
        return str(self)


class ChromeEngine:
    START_PORT = 9345
    DEFAULT_WORKERS_AMOUNT = 2
    ERRORS_NOT_HANDLED = (KeyboardInterrupt,)

    def __init__(self, max_concurrent_tabs=None, **daemon_kwargs):
        self._q: typing.Union[asyncio.PriorityQueue, asyncio.Queue] = None
        self._shutdown = False
        # max tab currency num
        self._workers: typing.List[ChromeWorker] = []
        self.max_concurrent_tabs = max_concurrent_tabs
        self.daemon_kwargs = daemon_kwargs

    @property
    def workers(self):
        return self._workers

    @property
    def q(self):
        if not self._q:
            self._q = asyncio.PriorityQueue()
        return self._q

    def _add_default_workers(self):
        for offset in range(self.DEFAULT_WORKERS_AMOUNT):
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

    async def do(self, data, tab_callback, timeout: float = None):
        if self._shutdown:
            raise RuntimeError('ChromeEngine has been shutdown.')
        future = ExpireFuture(data, tab_callback, timeout=timeout)
        await self.q.put(future)
        try:
            return await asyncio.wait_for(future, timeout=future.timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            del future

    async def shutdown(self):
        if self._shutdown:
            return
        for _ in self.workers:
            await self.q.put(ExpireFuture(ChromeWorker.STOP_SIG, 0))
        self._shutdown = True
        for worker in self.workers:
            await worker.shutdown()
        return self

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        return await self.shutdown()


class ChromeUtilsMixin(object):
    pass
