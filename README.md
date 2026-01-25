[ichrome](https://github.com/ClericPy/ichrome) [![PyPI](https://img.shields.io/pypi/v/ichrome?style=plastic)](https://pypi.org/project/ichrome/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/ichrome?style=plastic)![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ichrome?style=plastic)![PyPI - Downloads](https://img.shields.io/pypi/dm/ichrome?style=plastic)![PyPI - License](https://img.shields.io/pypi/l/ichrome?style=plastic)

----------

> Chrome controller for Humans, based on [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/) and python3.8+. [Read Docs](https://clericpy.github.io/ichrome/)

**🚀 [NEW] ichrome v6.0.0 is available! Now supporting `ichrome.http` - a RESTful API server to control Chrome via HTTP requests.**

> `uvx --from ichrome ichrome.http`  
> or  
> `python -m ichrome.http`  
> then view the interactive API docs at `http://localhost:8080/docs`

![image](https://github.com/ClericPy/ichrome/raw/master/structure.png)

> If you encounter any problems, please let me know through [issues](https://github.com/ClericPy/ichrome/issues); your feedback is valuable for enhancing `ichrome`.


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


# Why?

- In desperate need of a stable toolkit to communicate with Chrome browser (or other Blink-based browsers such as Chromium)
  - `ichrome` includes fast http & websocket connections (based on aiohttp) within an **asyncio** environment
- Pyppeteer is awesome
  - But I don't need so much, and the spelling of 'pyppeteer' is confusing
  - Event-driven architecture (EDA) is not always ideal.
- Selenium is slow
  - Webdriver often comes with memory leaks
    - PhantomJS development is suspended
  - No native coroutine (`asyncio`) support
- Playwright arrived too late
  - This may be a good choice for both `sync` and `async` usage
    - The original author of `puppeteer` joined the team.
  - But its core code is based on Node.js, which is hard to monkey-patch.

# Features

> As we know, **`Javascript` is the first-class citizen of the Browser world**, so learn to use it frequently with `ichrome`.

- A process daemon for Chrome instances
  - **auto-restart**
  - command-line usage
  - `async` environment compatible
- Connect to an **existing** Chrome
- Operations on Tabs under stable `websocket`
  - Commonly used functions
  - `Incognito Mode`
- `ChromeEngine` as the process pool
  - support HTTP `api` router with [aiohttp](https://docs.aiohttp.org/en/stable/)
    - `python -m ichrome.http` or `uvx ichrome.http`
    - `python -m ichrome.http --help` for usage
  - ~~`python -m ichrome.web` (Removed since v6.0.0)~~

- `Flatten` mode with `sessionId`
  - Create only **1** WebSocket connection
  - New in version 2.9.0
    - [EXPERIMENTAL](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-attachToTarget)
    - Share the same `Websocket` connection and use `sessionId` to distinguish requests
  - After v3.0.1
    - `AsyncTab._DEFAULT_FLATTEN = True`
- The install script of chromium
- debug mode for sync usage with `ichrome.debugger` >4.0.0 (EXPERIMENTAL)

# Breaking Changes
1. v6.0.0
   1. `ichrome.web` module is removed, use ichrome.http instead.
   2. refactor the `ChromeEngine` method parameters.
      1. add `wait` condition before engine.do
