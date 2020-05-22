[ichrome](https://github.com/ClericPy/ichrome) [![PyPI](https://img.shields.io/pypi/v/ichrome?style=plastic)](https://pypi.org/project/ichrome/)![PyPI - Wheel](https://img.shields.io/pypi/wheel/ichrome?style=plastic)![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ichrome?style=plastic)![PyPI - Downloads](https://img.shields.io/pypi/dm/ichrome?style=plastic)![PyPI - License](https://img.shields.io/pypi/l/ichrome?style=plastic)
==============================================

> A connector to control Chrome browser ([Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/)), for python3.7+.

# Install

> Install from [PyPI](https://pypi.org/project/ichrome/)

    pip install ichrome -U

> Uninstall & clear the user data

        $ python3 -m ichrome --clean
        $ pip uninstall ichrome

# Why?

- pyppeteer / selenium is awesome, but I don't need so much
  - spelling of pyppeteer is confused.
  - selenium is slow.
- async communication with Chrome remote debug port, stable choice. [Recommended]
- sync way to test CDP,  which is not recommended for complex production environments. [Deprecated]
  - **ichrome.debugger** is a sync tool and depends on the `ichrome.async_utils`, which may be a better choice.


# Features

- Chrome process daemon
- Connect to existing chrome debug port
- Operations on Tabs


<details>
    <summary><b>AsyncChrome feature list</b></summary>

1. server
    > return `f"http://{self.host}:{self.port}"`, such as `http://127.0.0.1:9222`
1. version
    > version info from `/json/version` format like:
    ```
    {'Browser': 'Chrome/77.0.3865.90', 'Protocol-Version': '1.3', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'V8-Version': '7.7.299.11', 'WebKit-Version': '537.36 (@58c425ba843df2918d9d4b409331972646c393dd)', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/b5fbd149-959b-4603-b209-cfd26d66bdc1'}
    ```
1. `connect` / `check` / `ok`
    > check alive
1. `get_tabs` / `tabs` / `get_tab` / `get_tabs`
    > get the `AsyncTab` instance from `/json`.
1. `new_tab` / `activate_tab` / `close_tab` / `close_tabs`
    > operating tabs.
1. `close_browser`
    > find the activated tab and send `Browser.close` message, close the connected chrome browser gracefully.
    ```python
    await chrome.close_browser()
    ```
1. `kill`
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

</details>


<details>
    <summary><b>AsyncTab feature list</b></summary>

1. `set_url` / `reload`
    > navigate to a new url. `reload` equals to `set_url(None)`
1. `wait_event`
    > listening the events with given name, and separate from other same-name events with filter_function, finally run the callback_function with result.
1. `wait_page_loading` / `wait_loading`
    > wait for `Page.loadEventFired` event, or stop loading while timeout. Different from `wait_loading_finished`.
1. `wait_response` / `wait_request`
    > filt the `Network.responseReceived` / `Network.requestWillBeSent` event by `filter_function`, return the `request_dict` which can be used by `get_response` / `get_response_body` / `get_request_post_data`. WARNING: requestWillBeSent event fired do not mean the response is ready, should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
1. `wait_request_loading` / `wait_loading_finished`
    > sometimes event got `request_dict` with `wait_response`, but the ajax request is still fetching, which need to wait the `Network.loadingFinished` event.
1. `activate` / `activate_tab`
    > activate tab with websocket / http message.
1. `close` / `close_tab`
    > close tab with websocket / http message.
1. `add_js_onload`
    > `Page.addScriptToEvaluateOnNewDocument`, which means this javascript code will be run before page loaded.
1. `clear_browser_cache` / `clear_browser_cookies`
    > `Network.clearBrowserCache` and `Network.clearBrowserCookies`
1. `querySelectorAll`
    > get the tag instance, which contains the `tagName, innerHTML, outerHTML, textContent, attributes` attrs.
1. `click`
    > click the element queried by given *css selector*.
1. `refresh_tab_info`
    > to refresh the init attrs: `url`, `title`.
1. `current_html` / `current_title` / `current_url`
    > get the current html / title / url with `tab.js`. or using the `refresh_tab_info` method and init attrs.
1. `crash`
    > `Page.crash`
1. `get_cookies` / `get_all_cookies` / `delete_cookies` / `set_cookie`
    > some page cookies operations.
1. `set_headers` / `set_ua`
    > `Network.setExtraHTTPHeaders` and `Network.setUserAgentOverride`, used to update headers dynamically.
1. `close_browser`
    > send `Browser.close` message to close the chrome browser gracefully.
1. `get_bounding_client_rect` / `get_element_clip`
    > `get_element_clip` is alias name for the other, these two method is to get the rect of element which queried by css element.
1. `screenshot` / `screenshot_element`
    > get the screenshot base64 encoded image data. `screenshot_element` should be given a css selector to locate the element.
1. `get_page_size` / `get_screen_size`
    > size of current window or the whole screen.
1. `get_response`
    > get the response body with the given request dict.
1. `js`
    > run the given js code, return the raw response from sending `Runtime.evaluate` message.
1. `inject_js_url`
    > inject some js url, like `<script src="xxx/static/js/jquery.min.js"></script>` do.
1. `get_value` & `get_variable`
    > run the given js variable or expression, and return the result.
    ```python
    await tab.get_value('document.title')
    await tab.get_value("document.querySelector('title').innerText")
    ```
8. `keyboard_send`
    > dispath key event with `Input.dispatchKeyEvent`
9. `mouse_click`
    > dispath click event on given position
1. `mouse_drag`
    > dispath drag event on given position, and return the target x, y. `duration` arg is to slow down the move speed.
1. `mouse_drag_rel`
    > dispath drag event on given offset, and return the target x, y.
1. `mouse_drag_rel`
    > drag with offsets continuously.
    ```python
    await tab.set_url('https://draw.yunser.com/')
    walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
        0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
    await walker.move(50 * 1.414, 50 * 1.414, 0.2)
    ```
1. `mouse_press` / `mouse_release` / `mouse_move` / `mouse_move_rel` / `mouse_move_rel_chain`
    > similar to the drag features. These mouse features is only dispatched events, not the real mouse action.
1. `history_back` / `history_forward` / `goto_history_relative` / `reset_history`
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
        # connect to an opened chrome
        async with AsyncChrome() as chrome:
            tab = await chrome.new_tab(url="https://github.com/ClericPy")
            # async with tab() as tab:
            # and `as tab` can be omitted
            async with tab():
                await tab.wait_loading(2)
                await tab.js("document.write('<h1>Document updated.</h1>')")
                await asyncio.sleep(1)
                # await tab.js('alert("test ok")')
                print('output:', await tab.html)
                # output: <html><head></head><body><h1>Document updated.</h1></body></html>
                await tab.close()
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


Details:

    $ python3 -m ichrome --help

```
usage:
    All the unknown args will be appended to extra_config as chrome original args.

Demo:
    > python -m ichrome --host=127.0.0.1 --window-size=1212,1212 --incognito
    > ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': '127.0.0.1', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': False, 'start_url': 'about:blank', 'extra_config': ['--window-size=1212,1212', '--incognito'], 'max_deaths': 1, 'timeout': 2}

Other operations:
    1. kill local chrome process with given port:
        python -m ichrome -s 9222
    2. clear user_data_dir path (remove the folder and files):
        python -m ichrome --clear
        python -m ichrome --clean
    3. show ChromeDaemon.__doc__:
        python -m ichrome --doc
    4. crawl the URL, output the HTML DOM:
        python -m ichrome --crawl --headless --timeout=2 http://myip.ipip.net/

optional arguments:
  -h, --help            show this help message and exit
  -V, --version         ichrome version info
  -c CHROME_PATH, --chrome_path CHROME_PATH
                        chrome executable file path, default to null for
                        automatic searching
  --host HOST           --remote-debugging-address, default to 127.0.0.1
  -p PORT, --port PORT  --remote-debugging-port, default to 9222
  --headless            --headless and --hide-scrollbars, default to False
  -s SHUTDOWN, --shutdown SHUTDOWN
                        shutdown the given port, only for local running chrome
  --user_agent USER_AGENT
                        --user-agen, default to 'Mozilla/5.0 (Windows NT 10.0;
                        WOW64) AppleWebKit/537.36 (KHTML, like Gecko)
                        Chrome/70.0.3538.102 Safari/537.36'
  --proxy PROXY         --proxy-server, default to None
  --user_data_dir USER_DATA_DIR
                        user_data_dir to save the user data, default to
                        ~/ichrome_user_data
  --disable_image       disable image for loading performance, default to
                        False
  --start_url START_URL
                        start url while launching chrome, default to
                        about:blank
  --max_deaths MAX_DEATHS
                        max deaths in 5 secs, auto restart `max_deaths` times
                        if crash fast in 5 secs. default to 1 for without
                        auto-restart
  --timeout TIMEOUT     timeout to connect the remote server, default to 1 for
                        localhost
  --workers WORKERS     the number of worker processes with auto-increment
                        port, default to 1
  --proc_check_interval PROC_CHECK_INTERVAL
                        check chrome process alive every interval seconds
  --crawl               crawl the given URL, output the HTML DOM
  --clean, --clear      clean user_data_dir
  --doc                 show ChromeDaemon.__doc__
  --debug               set logger level to DEBUG
```

## Interactive Debugging

```python
λ python
Python 3.7.1 (v3.7.1:260ec2c36a, Oct 20 2018, 14:57:15) [MSC v.1915 64 bit (AMD64)] on win32
Type "help", "copyright", "credits" or "license" for more information.
>>> from ichrome.debugger import *
>>> tab = get_a_tab()
>>> tab.set_url('http://bing.com')
{'id': 4, 'result': {'frameId': 'DAC309349D270F07505C3DAB71084292', 'loaderId': '181418C22DB39654507D042627C22698'}}
>>> tab.click('#scpl0')
Tag(a)
>>> tab.js('document.getElementById("sb_form_q").value = "jordan"')
{'id': 16, 'result': {'result': {'type': 'string', 'value': 'jordan'}}}
>>> tab.click('#sb_form_go')
Tag(input)
>>> tab.history_back()
True
>>> tab.set_html('hello')
{'id': 17, 'result': {}}
>>> tab.set_ua('no UA')
INFO  2020-05-11 20:14:07 [ichrome] async_utils.py(790): [set_ua] <Tab(connected): 08F4AFF9B389B1D5880AF0C0988B6DD4> userAgent => no UA
{'id': 12, 'result': {}}
>>> tab.set_url('http://httpbin.org/user-agent')
{'id': 14, 'result': {'frameId': '08F4AFF9B389B1D5880AF0C0988B6DD4', 'loaderId': '15761B915F7AC36DC4687C1EED28195B'}}
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
- [ ] HTTP apis server console [fastapi]. (maybe a new lib)
- [ ] ~~Complete document.~~
