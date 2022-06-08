from .async_utils import AsyncChrome, AsyncTab
from .base import Tag
from .daemon import AsyncChromeDaemon, ChromeDaemon, ChromeWorkers
from .debugger import get_a_tab, repl
from .logs import logger
from .pool import ChromeEngine
from .sync_utils import Chrome, Tab

__version__ = "3.0.3"
__tips__ = "[github]: https://github.com/ClericPy/ichrome\n[cdp]: https://chromedevtools.github.io/devtools-protocol/\n[cmd args]: https://peter.sh/experiments/chromium-command-line-switches/"
__all__ = [
    'Chrome', 'ChromeDaemon', 'Tab', 'Tag', 'AsyncChrome', 'AsyncTab', 'logger',
    'AsyncChromeDaemon', 'ChromeWorkers', 'get_a_tab', 'ChromeEngine', 'repl'
]
