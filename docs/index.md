# Intro

# [ichrome](https://github.com/ClericPy/ichrome) [![PyPI](https://img.shields.io/pypi/v/ichrome?style=plastic)](https://pypi.org/project/ichrome/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/ichrome?style=plastic)![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ichrome?style=plastic)![PyPI - Downloads](https://img.shields.io/pypi/dm/ichrome?style=plastic)![PyPI - License](https://img.shields.io/pypi/l/ichrome?style=plastic)

-----------

> Chrome controller for Humans, based on [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/) and python3.8+.

**🚀 [NEW] ichrome v6.0.0 is available! Now supporting [ichrome.http](./reference/WebAPP.md) - a RESTful API server to control Chrome via HTTP requests.**

![image](https://github.com/ClericPy/ichrome/raw/master/structure.png)

If you encounter any problems, please let me know through [issues](https://github.com/ClericPy/ichrome/issues); your feedback is valuable for enhancing `ichrome`.

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
- `Flatten` mode with `sessionId`
    - Create only **1** WebSocket connection
    - New in version 2.9.0
        - [EXPERIMENTAL](https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-attachToTarget)
        - Share the same `Websocket` connection and use `sessionId` to distinguish requests
    - After v3.0.1
        - `AsyncTab._DEFAULT_FLATTEN = True`
- The install script of chromium
