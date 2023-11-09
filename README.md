[ichrome](https://github.com/ClericPy/ichrome) [![PyPI](https://img.shields.io/pypi/v/ichrome?style=plastic)](https://pypi.org/project/ichrome/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/ichrome?style=plastic)![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ichrome?style=plastic)![PyPI - Downloads](https://img.shields.io/pypi/dm/ichrome?style=plastic)![PyPI - License](https://img.shields.io/pypi/l/ichrome?style=plastic)

----------

> Chrome controller for Humans, base on [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/) and python3.7+. [Read Docs](https://clericpy.github.io/ichrome/)

![image](https://github.com/ClericPy/ichrome/raw/master/structure.png)

> If you encounter any problems, please let me know through [issues](https://github.com/ClericPy/ichrome/issues), some of them will be a good opinion for the enhancement of `ichrome`.


# Install

    pip install ichrome -U

> Uninstall & Clear the user data folder

        $ python3 -m ichrome --clean
        $ pip uninstall ichrome

## Quick Start

```python
import asyncio
from ichrome import AsyncChromeDaemon


async def test():
    async with AsyncChromeDaemon() as cd:
        # create a new tab
        async with cd.connect_tab(index=None) as tab:
            await tab.goto('https://github.com/ClericPy/ichrome', timeout=5)
            print(await tab.title)
        # Privacy Mode, proxyServer arg maybe not work on Chrome, for `Target.createBrowserContext` is the EXPERIMENTAL feature(but chromium is ok).
        # https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-createBrowserContext
        async with cd.incognito_tab(proxyServer='http://127.0.0.1:8080') as tab:
            await tab.goto('https://httpbin.org/ip', timeout=5)
            print(await tab.html)


asyncio.run(test())
```

### [Read Docs](https://clericpy.github.io/ichrome/)

# Why?

- In desperate need of a stable toolkit to communicate with Chrome browser (or other Blink-based browsers such as Chromium)
  - `ichrome` includes fast http & websocket connections (based on aiohttp) within an **asyncio** environment
- Pyppeteer is awesome
  - But I don't need so much, and the spelling of pyppeteer is confused
  - Event-driven architecture(EDA) is not always smart.
- Selenium is slow
  - Webdriver often comes with memory leak
    - PhantomJS development is suspended
  - No native coroutine(`asyncio`) support
- Playwright comes too late
  - This may be a good choice for both `sync` and `async` usage
    - The 1st author of `puppeteer` joined it.
  - But its core code is based on Node.js, which is too hard to monkey-patch.

# Features

> As we known, **`Javascript` is the first-class citizen of the Browser world**, so learn to use it with `ichrome` frequently.

- A process daemon of Chrome instances
  - **auto-restart**
  - command-line usage
  - `async` environment compatible
- Connect to an **existing** Chrome
- Operations on Tabs under stable `websocket`
  - Commonly used functions
  - `Incognito Mode`
- `ChromeEngine` as the progress pool
  - support HTTP `api` router with [FastAPI](https://github.com/tiangolo/fastapi) (EXPERIMENTAL)
    - launch the chrome pool with `python -m ichrome.web`
      - `python -m ichrome.web --help` for usage
- `Flatten` mode with `sessionId`
  - Create only **1** WebSocket connection
  - New in version 2.9.0
    - [EXPERIMENTAL](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-attachToTarget)
    - Share the same `Websocket` connection and use `sessionId` to distinguish requests
  - After v3.0.1
    - `AsyncTab._DEFAULT_FLATTEN = True`
- The install script of chromium
- debug mode for sync usage with `ichrome.debugger` >4.0.0 (EXPERIMENTAL)
