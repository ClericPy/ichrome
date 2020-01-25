from .base import Chrome, ChromeDaemon, Tab, Tag
from .logs import logger
from .async_utils import Chrome as AsyncChrome, Tab as AsyncTab
__version__ = "0.2.5"
__tips__ = "[github]: https://github.com/ClericPy/ichrome\n[cdp]: https://chromedevtools.github.io/devtools-protocol/\n[cmd args]: https://peter.sh/experiments/chromium-command-line-switches/"
__all__ = [
    'Chrome', 'ChromeDaemon', 'Tab', 'Tag', 'AsyncChrome', 'AsyncTab', 'logger'
]
