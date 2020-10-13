[ichrome](https://github.com/ClericPy/ichrome) [![PyPI](https://img.shields.io/pypi/v/ichrome?style=plastic)](https://pypi.org/project/ichrome/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/ichrome?style=plastic)![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ichrome?style=plastic)![PyPI - Downloads](https://img.shields.io/pypi/dm/ichrome?style=plastic)![PyPI - License](https://img.shields.io/pypi/l/ichrome?style=plastic)
==============================================

> Chrome controller for Humans, base on [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/) and python3.7+.

![image](https://github.com/ClericPy/ichrome/raw/master/structure.png)

# Why?

- Pyppeteer is awesome, but I don't need so much
  - spelling of pyppeteer is confused
  - event-driven programming is not always advisable.
- Selenium is slow
  - webdrivers often come with memory leak.
- In desperate need of a stable toolkit to communicate with Chrome browser (or other Blink-based browsers like Chromium)
  - fast http & websocket connections (based on aiohttp) for **asyncio** environment
  - **ichrome.debugger** is a sync tool and depends on the `ichrome.async_utils`
    - a choice for debugging interactively.

# Features

- Chrome process daemon
  - auto-restart
  - command-line usage support
  - async environment compatible
- Connect to an existing Chrome
- Operations on Tabs under stable websocket
  - Package very commonly used functions
- **ChromeEngine** progress pool utils
  - support HTTP api router with [FastAPI](https://github.com/tiangolo/fastapi)


# What's More?

As we known, `Chrome` browsers (including various webdriver versions) will have the following problems **in a long-running scene**:
   1. memory leak
   2. missing websocket connections
   3. infinitely growing cache
   4. other unpredictable problems...

So you may need a more stable process pool with **ChromeEngine(HTTP usage & normal usage)**:

<details>
    <summary><b>Show more</b></summary>

## ChromeEngine HTTP usage

### Server

> pip install -U ichrome[web]

```python
import uvicorn
from fastapi import FastAPI

from ichrome.routers.fastapi_routes import ChromeAPIRouter

app = FastAPI()
app.include_router(ChromeAPIRouter(headless=True), prefix='/chrome')

uvicorn.run(app)

# view url with your browser
# http://127.0.0.1:8000/chrome/screenshot?url=http://bing.com
# http://127.0.0.1:8000/chrome/download?url=http://bing.com
# http://127.0.0.1:8000/chrome/js?url=http://bing.com&js=document.title
```

### Client

```python
from torequests import tPool
from inspect import getsource
req = tPool()


async def tab_callback(self, tab, data, timeout):
    await tab.set_url(data['url'], timeout=timeout)
    return (await tab.querySelector('h1')).text


r = req.post('http://127.0.0.1:8000/chrome/do',
             json={
                 'data': {
                     'url': 'http://httpbin.org/html'
                 },
                 'tab_callback': getsource(tab_callback),
                 'timeout': 10
             })
print(r.text)
# "Herman Melville - Moby-Dick"
```


## ChromeEngine normal usage

### Connect tab and do something
```python
import asyncio

from ichrome.pool import ChromeEngine


def test_chrome_engine_connect_tab():

    async def _test_chrome_engine_connect_tab():

        async with ChromeEngine(port=9234, headless=True,
                                disable_image=True) as ce:
            async with ce.connect_tab(port=9234) as tab:
                await tab.goto('http://pypi.org')
                print(await tab.title)

    asyncio.get_event_loop().run_until_complete(
        _test_chrome_engine_connect_tab())


if __name__ == "__main__":
    test_chrome_engine_connect_tab()
# INFO  2020-10-13 22:18:53 [ichrome] pool.py(464): [enqueue](0) ChromeTask(<9234>, PENDING, id=1, tab=None), timeout=None, data=<ichrome.pool._TabWorker object at 0x000002232841D9A0>
# INFO  2020-10-13 22:18:55 [ichrome] pool.py(172): [online] ChromeWorker(<9234>, 0/5, 0 todos) is online.
# INFO  2020-10-13 22:18:55 [ichrome] pool.py(200): ChromeWorker(<9234>, 0/5, 0 todos) get a new task ChromeTask(<9234>, PENDING, id=1, tab=None).
# PyPI · The Python Package Index
# INFO  2020-10-13 22:18:57 [ichrome] pool.py(182): [offline] ChromeWorker(<9234>, 0/5, 0 todos) is offline.
# INFO  2020-10-13 22:18:57 [ichrome] pool.py(241): [finished](0) ChromeTask(<9234>, PENDING, id=1, tab=None)
```

### Batch Tasks
```python
import asyncio
from inspect import getsource

from ichrome.pool import ChromeEngine


async def tab_callback(self, tab, url, timeout):
    await tab.set_url(url, timeout=5)
    return await tab.title


def test_pool():

    async def _test_pool():
        async with ChromeEngine(max_concurrent_tabs=5,
                                headless=True,
                                disable_image=True) as ce:
            tasks = [
                asyncio.ensure_future(
                    ce.do('http://bing.com', tab_callback, timeout=10))
                for _ in range(3)
            ] + [
                asyncio.ensure_future(
                    ce.do(
                        'http://bing.com', getsource(tab_callback), timeout=10))
                for _ in range(3)
            ]
            for task in tasks:
                result = await task
                print(result)
                assert result

    # asyncio.run will raise aiohttp issue: https://github.com/aio-libs/aiohttp/issues/4324
    asyncio.get_event_loop().run_until_complete(_test_pool())


if __name__ == "__main__":
    test_pool()
```

</details>


# Install

> Install from [PyPI](https://pypi.org/project/ichrome/)

    pip install ichrome -U

> Uninstall & Clear the user data dir

        $ python3 -m ichrome --clean
        $ pip uninstall ichrome

<details>
    <summary><b>AsyncChrome feature list</b></summary>

1. server
    
    > return `f"http://{self.host}:{self.port}"`, such as `http://127.0.0.1:9222`
2. version
    > version info from `/json/version` format like:
    ```
    {'Browser': 'Chrome/77.0.3865.90', 'Protocol-Version': '1.3', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'V8-Version': '7.7.299.11', 'WebKit-Version': '537.36 (@58c425ba843df2918d9d4b409331972646c393dd)', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/b5fbd149-959b-4603-b209-cfd26d66bdc1'}
    ```
3. `connect` / `check` / `ok`
    
    > check alive
4. `get_tabs` / `tabs` / `get_tab` / `get_tabs`
    
    > get the `AsyncTab` instance from `/json`.
5. `new_tab` / `activate_tab` / `close_tab` / `close_tabs`
    
    > operating tabs.
6. `close_browser`
    > find the activated tab and send `Browser.close` message, close the connected chrome browser gracefully.
    ```python
    await chrome.close_browser()
    ```
7. `kill`
    > force kill the chrome process with self.port.
    ```python
    await chrome.kill()
    ```
1. `connect_tabs`
    > connect websockets for multiple tabs in one `with` context, and disconnect before exiting.
    ```python
    tab0: AsyncTab = (await chrome.tabs)[0]
    tab1: AsyncTab = await chrome.new_tab()
    async with chrome.connect_tabs([tab0, tab1]):
        assert (await tab0.current_url) == 'about:blank'
        assert (await tab1.current_url) == 'about:blank'
    ```
1. `connect_tab`
    > The easiest way to get a connected tab.
    > get an existing tab
    ```python
    async with chrome.connect_tab(0) as tab:
        print(await tab.current_title)
    ```
    > get a new tab and auto close it
    ```python
    async with chrome.connect_tab(None, True) as tab:
        print(await tab.current_title)
    ```
    > get a new tab with given url and auto close it
    ```python
    async with chrome.connect_tab('http://python.org', True) as tab:
        print(await tab.current_title)
    ```
</details>


<details>
    <summary><b>AsyncTab feature list</b></summary>

1. `set_url` / `reload`
    
    > navigate to a new url(return bool for whether load finished), or send `Page.reload` message.
2. `wait_event`
    
    > listening the events with given name, and separate from other same-name events with filter_function, finally run the callback_function with result.
3. `wait_page_loading` / `wait_loading`
    
    > wait for `Page.loadEventFired` event, or stop loading while timeout. Different from `wait_loading_finished`.
4. `wait_response` / `wait_request`
    
    > filt the `Network.responseReceived` / `Network.requestWillBeSent` event by `filter_function`, return the `request_dict` which can be used by `get_response` / `get_response_body` / `get_request_post_data`. WARNING: requestWillBeSent event fired do not mean the response is ready, should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
5. `wait_request_loading` / `wait_loading_finished`
    
    > sometimes event got `request_dict` with `wait_response`, but the ajax request is still fetching, which need to wait the `Network.loadingFinished` event.
6. `activate` / `activate_tab`
    
    > activate tab with websocket / http message.
7. `close` / `close_tab`
    
    > close tab with websocket / http message.
8. `add_js_onload`
    
    > `Page.addScriptToEvaluateOnNewDocument`, which means this javascript code will be run before page loaded.
9. `clear_browser_cache` / `clear_browser_cookies`
    
    > `Network.clearBrowserCache` and `Network.clearBrowserCookies`
10. `querySelectorAll`
    
    > get the tag instance, which contains the `tagName, innerHTML, outerHTML, textContent, attributes` attrs.
11. `click`
    
    > click the element queried by given *css selector*.
12. `refresh_tab_info`
    
    > to refresh the init attrs: `url`, `title`.
13. `current_html` / `current_title` / `current_url`
    
    > get the current html / title / url with `tab.js`. or using the `refresh_tab_info` method and init attrs.
14. `crash`
    
    > `Page.crash`
15. `get_cookies` / `get_all_cookies` / `delete_cookies` / `set_cookie`
    
    > some page cookies operations.
16. `set_headers` / `set_ua`
    
    > `Network.setExtraHTTPHeaders` and `Network.setUserAgentOverride`, used to update headers dynamically.
17. `close_browser`
    
    > send `Browser.close` message to close the chrome browser gracefully.
18. `get_bounding_client_rect` / `get_element_clip`
    
    > `get_element_clip` is alias name for the other, these two method is to get the rect of element which queried by css element.
19. `screenshot` / `screenshot_element`
    
    > get the screenshot base64 encoded image data. `screenshot_element` should be given a css selector to locate the element.
20. `get_page_size` / `get_screen_size`
    
    > size of current window or the whole screen.
21. `get_response`
    
    > get the response body with the given request dict.
22. `js`
    
    > run the given js code, return the raw response from sending `Runtime.evaluate` message.
23. `inject_js_url`
    
    > inject some js url, like `<script src="xxx/static/js/jquery.min.js"></script>` do.
24. `get_value` & `get_variable`
    > run the given js variable or expression, and return the result.
    ```python
    await tab.get_value('document.title')
    await tab.get_value("document.querySelector('title').innerText")
    ```
25. `keyboard_send`
    
    > dispath key event with `Input.dispatchKeyEvent`
26. `mouse_click`
    
    > dispath click event on given position
27. `mouse_drag`
    
    > dispath drag event on given position, and return the target x, y. `duration` arg is to slow down the move speed.
28. `mouse_drag_rel`
    
    > dispath drag event on given offset, and return the target x, y.
29. `mouse_drag_rel`
    > drag with offsets continuously.
    ```python
    await tab.set_url('https://draw.yunser.com/')
    walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
        0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
    await walker.move(50 * 1.414, 50 * 1.414, 0.2)
    ```
30. `mouse_press` / `mouse_release` / `mouse_move` / `mouse_move_rel` / `mouse_move_rel_chain`
    
    > similar to the drag features. These mouse features is only dispatched events, not the real mouse action.
31. `history_back` / `history_forward` / `goto_history_relative` / `reset_history`
    
    > back / forward history

</details>

# Examples

### See the [Classic Use Cases](https://github.com/ClericPy/ichrome/blob/master/use_cases.py)

## Quick Start

1. Start a new chrome daemon process with headless=False

        python -m ichrome

   or launch chrome daemon in code

        async with AsyncChromeDaemon():

2. Create the connection to exist chrome browser
   
        async with AsyncChrome() as chrome:

3. Operations on the tabs: new tab, wait loading, run javascript, get html, close tab
4. Close the browser GRACEFULLY instead of killing process

```python
from ichrome import AsyncChromeDaemon, AsyncChrome
import asyncio


async def main():
    # If there is an existing daemon, such as `python -m ichrome`, the `async with AsyncChromeDaemon` context can be omitted.
    async with AsyncChromeDaemon():
        # connect to an opened chrome, default host=127.0.0.1, port=9222, headless=False
        async with AsyncChrome() as chrome:
            # If you need reuse an existing tab, set index with int like 0 for activated tab, such as `async with chrome.connect_tab(0) as tab:`
            async with chrome.connect_tab(index='https://github.com/ClericPy',
                                          auto_close=True) as tab:
                await tab.wait_loading(2)
                await tab.js("document.write('<h1>Document updated.</h1>')")
                await asyncio.sleep(1)
                # await tab.js('alert("test ok")')
                print('output:', await tab.html)
                # output: <html><head></head><body><h1>Document updated.</h1></body></html>
                # will auto_close tab while exiting context
                # await tab.close()
            # close_browser gracefully, I have no more need of chrome instance
            await chrome.close_browser()


if __name__ == "__main__":
    asyncio.run(main())
```

[More Examples](https://github.com/ClericPy/ichrome/blob/master/examples_async.py)

## Command Line Usage

> Be used for launching a chrome daemon process. The unhandled args will be treated as chrome raw args and appended to extra_config list.
> 
> [Chromium Command Line Args List](https://peter.sh/experiments/chromium-command-line-switches/)

Shutdown Chrome process with the given port
```bash
λ python3 -m ichrome -s 9222
2018-11-27 23:01:59 DEBUG [ichrome] base.py(329): kill chrome.exe --remote-debugging-port=9222
2018-11-27 23:02:00 DEBUG [ichrome] base.py(329): kill chrome.exe --remote-debugging-port=9222
```
Launch a Chrome daemon process
```bash
λ python3 -m ichrome -p 9222 --start_url "http://bing.com" --disable_image
2018-11-27 23:03:57 INFO  [ichrome] __main__.py(69): ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': 'localhost', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': True, 'start_url': 'http://bing.com', 'extra_config': '', 'max_deaths': 1, 'timeout': 2}
```
Crawl the given URL, output the HTML DOM
```bash
λ python3 -m ichrome --crawl --headless --timeout=2 http://api.ipify.org/
<html><head></head><body><pre style="word-wrap: break-word; white-space: pre-wrap;">38.143.68.66</pre></body></html>
```
To use default user dir (ignore ichrome user-dir settings)
> ensure the existing Chromes get closed
```bash
λ python -m ichrome -U null
```

Details:

    $ python3 -m ichrome --help

```
usage:
    All the unknown args will be appended to extra_config as chrome original args.

Demo:
    > python -m ichrome -H 127.0.0.1 -p 9222 --window-size=1212,1212 --incognito
    > ChromeDaemon cmd args: port=9222, {'chrome_path': '', 'host': '127.0.0.1', 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': WindowsPath('C:/Users/root/ichrome_user_data'), 'disable_image': False, 'start_url': 'about:blank', 'extra_config': ['--window-size=1212,1212', '--incognito'], 'max_deaths': 1, 'timeout':1, 'proc_check_interval': 5, 'debug': False}

    > python -m ichrome
    > ChromeDaemon cmd args: port=9222, {'chrome_path': '', 'host': '127.0.0.1', 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': WindowsPath('C:/Users/root/ichrome_user_data'), 'disable_image': False, 'start_url': 'about:blank', 'extra_config': [], 'max_deaths': 1, 'timeout': 1, 'proc_check_interval': 5, 'debug': False}

Other operations:
    1. kill local chrome process with given port:
        python -m ichrome -s 9222
        python -m ichrome -k 9222
    2. clear user_data_dir path (remove the folder and files):
        python -m ichrome --clear
        python -m ichrome --clean
        python -m ichrome -C -p 9222
    3. show ChromeDaemon.__doc__:
        python -m ichrome --doc
    4. crawl the URL, output the HTML DOM:
        python -m ichrome --crawl --headless --timeout=2 http://myip.ipip.net/

optional arguments:
  -h, --help            show this help message and exit
  -v, -V, --version     ichrome version info
  -c CONFIG, --config CONFIG
                        load config dict from JSON file of given path
  -cp CHROME_PATH, --chrome-path CHROME_PATH, --chrome_path CHROME_PATH
                        chrome executable file path, default to null for
                        automatic searching
  -H HOST, --host HOST  --remote-debugging-address, default to 127.0.0.1
  -p PORT, --port PORT  --remote-debugging-port, default to 9222
  --headless            --headless and --hide-scrollbars, default to False
  -s SHUTDOWN, -k SHUTDOWN, --shutdown SHUTDOWN
                        shutdown the given port, only for local running chrome
  -A USER_AGENT, --user-agent USER_AGENT, --user_agent USER_AGENT
                        --user-agent, default to Chrome PC: Mozilla/5.0
                        (Linux; Android 6.0; Nexus 5 Build/MRA58N)
                        AppleWebKit/537.36 (KHTML, like Gecko)
                        Chrome/83.0.4103.106 Mobile Safari/537.36
  -x PROXY, --proxy PROXY
                        --proxy-server, default to None
  -U USER_DATA_DIR, --user-data-dir USER_DATA_DIR, --user_data_dir USER_DATA_DIR
                        user_data_dir to save user data, default to
                        ~/ichrome_user_data
  --disable-image, --disable_image
                        disable image for loading performance, default to
                        False
  -url START_URL, --start-url START_URL, --start_url START_URL
                        start url while launching chrome, default to
                        about:blank
  --max-deaths MAX_DEATHS, --max_deaths MAX_DEATHS
                        restart times. default to 1 for without auto-restart
  --timeout TIMEOUT     timeout to connect the remote server, default to 1 for
                        localhost
  -w WORKERS, --workers WORKERS
                        the number of worker processes, default to 1
  --proc-check-interval PROC_CHECK_INTERVAL, --proc_check_interval PROC_CHECK_INTERVAL
                        check chrome process alive every interval seconds
  --crawl               crawl the given URL, output the HTML DOM
  -C, --clear, --clear  clean user_data_dir
  --doc                 show ChromeDaemon.__doc__
  --debug               set logger level to DEBUG
  -K, --killall         killall chrome launched local with --remote-debugging-
                        port
```

## Interactive Debugging

```python
λ python
Python 3.7.1 (v3.7.1:260ec2c36a, Oct 20 2018, 14:57:15) [MSC v.1915 64 bit (AMD64)] on win32
Type "help", "copyright", "credits" or "license" for more information.
>>> from ichrome.debugger import *
>>> tab = get_a_tab()
>>> tab.set_url('https://github.com/ClericPy')
True
>>> tab.click('.pinned-item-list-item-content [href="/ClericPy/ichrome"]')
Tag(a)
>>> tab.wait_loading(2)
True
>>> tab.wait_loading(2)
False
>>> tab.js('document.body.innerHTML="Updated"')
{'type': 'string', 'value': 'Updated'}
>>> tab.history_back()
True
>>> tab.set_html('hello world')
{'id': 21, 'result': {}}
>>> tab.set_ua('no UA')
{'id': 22, 'result': {}}
>>> tab.set_url('http://httpbin.org/user-agent')
True
>>> tab.html
'<html><head></head><body><pre style="word-wrap: break-word; white-space: pre-wrap;">{\n  "user-agent": "no UA"\n}\n</pre></body></html>'
```


## [Debugger] debug the features of async Chrome / Tab / Daemon.

> Similar to sync usage, but methods come from the AsyncChrome / AsyncTab / AsyncDaemon

Test Code: [examples_debug.py](https://github.com/ClericPy/ichrome/blob/master/examples_debug.py)

## Operating tabs with coroutines in the async environment

> Run in a completely asynchronous environment, it's a stable choice.

Test Code: [examples_async.py](https://github.com/ClericPy/ichrome/blob/master/examples_async.py)

## [Archived] Simple Sync Usage

> Sync utils will be hardly maintained, no more new features.

Test Code: [examples_sync.py](https://github.com/ClericPy/ichrome/blob/master/examples_sync.py)


## TODO

- [x] ~~Concurrent support. (gevent, threading, asyncio)~~
- [x] Add auto_restart while crash.
- [ ] ~~Auto remove the zombie tabs with a lifebook.~~
- [x] Add some useful examples.
- [x] Coroutine support (for asyncio).
- [x] Standard test cases.
- [x] Stable Chrome Process Pool.
- [x] HTTP apis server console with [FastAPI](https://github.com/tiangolo/fastapi).
- [ ] Complete the document.
