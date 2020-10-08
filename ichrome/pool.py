import asyncio
import random
import time
import typing
from copy import deepcopy
from ichrome import AsyncChromeDaemon, AsyncTab
from ichrome.exceptions import ChromeException
from ichrome.logs import logger
from inspect import isawaitable


class ExpireFuture(asyncio.Future):
    # like: float('inf')
    MAX_TIMEOUT = 10**10
    _ID = 0
    EXEC_GLOBALS: typing.Dict[str, typing.Any] = {}
    EXEC_LOCALS: typing.Dict[str, typing.Any] = {}

    def __init__(self, data, tab_worker: typing.Callable = None, timeout=None):
        super().__init__()
        self.id = self.get_id()
        self.data = data
        self.timeout = self.MAX_TIMEOUT if timeout is None else timeout
        self.expire_time = time.time() + self.timeout
        self.tab_worker = self.ensure_function(tab_worker)
        self._running_task = None

    def ensure_function(self, tab_worker):
        if tab_worker and isinstance(tab_worker, str):
            tab_worker = exec(tab_worker, self.EXEC_GLOBALS, self.EXEC_LOCALS)
        return tab_worker or self._do_nothing

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

    async def _do_nothing(self, tab: AsyncTab, data):
        return (tab, data)

    async def run(self, tab: AsyncTab):
        _result = self.tab_worker(tab, self.data)
        if isawaitable(_result):
            _result = await _result
        self.set_result(_result)

    @property
    def timeleft(self):
        return time.time() - self.expire_time

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __str__(self):
        return f'ChromeTask<{self.id}>'

    def __repr__(self) -> str:
        return str(self)


class ChromeWorker:
    STOP_SIG = object()
    DEFAULT_DAEMON_KWARGS: typing.Dict[str, typing.Any] = {}
    MAX_TAB_WORKERS = 5

    def __init__(self,
                 port=None,
                 max_tab_workers: int = None,
                 q: asyncio.PriorityQueue = None,
                 **daemon_kwargs):
        assert q, 'queue should not be null'
        self.port = port
        self.q = q
        self.max_tab_workers = max_tab_workers or self.MAX_TAB_WORKERS
        self._tab_sem = None
        self._shutdown = False
        self.daemon_kwargs = daemon_kwargs or deepcopy(
            self.DEFAULT_DAEMON_KWARGS)
        assert 'port' not in self.daemon_kwargs, 'invalid key `port` for self.daemon_kwargs'
        self.daemon_task = None
        self.consumers: typing.List[asyncio.Task] = []

    def start_daemon(self):
        self._ready_event = asyncio.Event()
        self._need_restart = asyncio.Event()
        self.daemon_task = asyncio.ensure_future(self._start_tab_worker())
        self.consumers = [
            asyncio.ensure_future(self.future_consumer())
            for _ in range(self.max_tab_workers)
        ]
        return self.daemon_task

    async def _start_tab_worker(self):
        while not self._shutdown:
            self._ready_event.clear()
            self._need_restart.clear()
            async with AsyncChromeDaemon(port=self.port,
                                         **self.daemon_kwargs) as chrome_daemon:
                self.chrome_daemon = chrome_daemon
                self._ready_event.set()
                logger.debug(f'{self} is ready.')
                await self._need_restart.wait()

    async def future_consumer(self):
        while not self._shutdown:
            await self._ready_event.wait()
            future: ExpireFuture = await self.q.get()
            if future.data is self.STOP_SIG:
                self._shutdown = True
                await self.q.put(future)
                return
            if await self.chrome_daemon._check_chrome_connection():
                async with self.chrome_daemon.connect_tab(
                        index=None, auto_close=True) as tab:
                    try:
                        await future.run(tab)
                        continue
                    except ChromeEngine.ERRORS_NOT_HANDLED as error:
                        raise error
                    except ChromeException as error:
                        logger.error(
                            f'{self} catch an error {error!r}, restarting')
                        self._need_restart.set()
                    except Exception as error:
                        logger.error(
                            f'{self} catch an error {error!r} for {future}')
            await self.q.put(future)

    def start_tab_worker(self):
        asyncio.ensure_future(self._start_tab_worker())

    async def shutdown(self):
        if self._shutdown:
            return
        # await self._shutdown()
        self._shutdown = True
        self._need_restart.set()
        await self.daemon_task
        for task in self.consumers:
            task.cancel()

    def get_random_secs(self, start=0, end=5):
        return random.choice(range(start * 1000, end * 1000)) / 1000

    def __str__(self):
        return f'ChromeWorker<{self.port}>'

    def __repr__(self) -> str:
        return str(self)


class ChromeEngine:
    START_PORT = 9345
    # auto restart chrome daemon every interval seconds, avoid zombie processes.
    SECONDS_BEFORE_RESTART = 8 * 60
    # auto restart chrome daemon after many tabs, avoid zombie processes.
    MAX_COUNT_BEFORE_RESTART = 800
    DEFAULT_WORKERS_AMOUNT = 2
    ERRORS_NOT_HANDLED = (KeyboardInterrupt,)

    def __init__(self, **daemon_kwargs):
        self._q: typing.Union[asyncio.PriorityQueue, asyncio.Queue] = None
        self._shutdown = False
        # max tab currency num
        self._workers: typing.List[ChromeWorker] = []
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
            worker = ChromeWorker(port=port, q=self.q, **self.daemon_kwargs)
            self.workers.append(worker)

    async def start_workers(self):
        if not self.workers:
            self._add_default_workers()
        for worker in self.workers:
            worker.start_daemon()
        return self

    async def start(self):
        return await self.start_workers()

    async def do(self, data, tab_worker, timeout: float = None):
        if self._shutdown:
            raise RuntimeError('ChromeEngine has been shutdown.')
        future = ExpireFuture(data, tab_worker)
        await self.q.put(future)
        try:
            return await asyncio.wait_for(future, timeout=future.timeout)
        except asyncio.TimeoutError:
            return None

    async def shutdown(self):
        if self._shutdown:
            return
        for _ in self.workers:
            await self.q.put(ExpireFuture(ChromeWorker.STOP_SIG, 0))
        self._shutdown = True
        for worker in self.workers:
            await worker.shutdown()

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        await self.shutdown()
        return self


class ChromeUtilsMixin(object):
    pass
