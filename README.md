# [ichrome - v0.1.2](https://github.com/ClericPy/ichrome)

> A toy for using chrome under the [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/). For python3.6+ (who cares python2.x).

## Install

> pip install ichrome -U

## Why?

- pyppeteer/selenium is awesome, but I don't need so much...

- one way to test CDP


## Features

- Chrome process daemon
- Connect to existing chrome debug port
- Operations on Tabs

## Examples


### Chrome daemon

```python
from ichrome import ChromeDaemon

def main():
    with ChromeDaemon() as chromed:
        # run_forever means auto_restart
        chromed.run_forever(0)
        chrome = Chrome()
        tab = chrome.new_tab()
        time.sleep(3)
        tab.close()

if __name__ == "__main__":
    main()
```

### Connect to existing debug port

```python
from ichrome import Chrome

def main():
    chrome = Chrome()
    print(chrome.tabs)
    # [ChromeTab("6EC65C9051697342082642D6615ECDC0", "about:blank", "about:blank", port: 9222)]
    print(chrome.tabs[0])
    # Tab(about:blank)

if __name__ == "__main__":
    main()
```

### Operations on Tab

```python
from ichrome import Chrome

import time


def main():
    chrome = Chrome()
    print(chrome.tabs)
    # [ChromeTab("6EC65C9051697342082642D6615ECDC0", "about:blank", "about:blank", port: 9222)]
    tab = chrome.tabs[0]
    # open a new page
    print(tab.set_url("http://p.3.cn/1", timeout=3))  # {"id":4,"result":{}}
    # reload page
    print(tab.reload())  # {"id":4,"result":{}}
    # Not recommended new_tab with url, use set_url can set a timeout to stop loading
    # tab = chrome.new_tab()
    # tab.set_url("http://p.3.cn", timeout=3)
    tab = chrome.new_tab("http://p.3.cn/new")
    time.sleep(1)
    print("404 Not Found" in tab.get_html("u8"))  # True
    print(tab.current_url)  # http://p.3.cn/new
    tab.close()


if __name__ == "__main__":
    main()

```

### Advanced Usage (Crawling a special background request.)

```python
"""
Test normal usage of ichrome.

1. use `with` context for launching ChromeDaemon daemon process.
2. init Chrome for connecting with chrome background server.
3. Tab ops:
  3.1 create a new tab
  3.2 goto new url with tab.set_url, and will stop load for timeout.
  3.3 get cookies from url
  3.4 inject the jQuery lib by a static url.
  3.5 auto click ok from the alert dialog.
  3.6 remove `href` from the third `a` tag, which is selected by css path.
  3.7 remove all `href` from the `a` tag, which is selected by css path.
  3.8 use querySelectorAll to get the elements.
  3.9 Network crawling from the background ajax request.
  3.10 click some element by tab.click with css selector.
  3.11 show html source code of the tab
"""


def example():
    import sys
    import os

    # use local ichrome module
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    os.chdir("..")  # for reuse exiting user data dir
    from ichrome import Chrome, Tab, ChromeDaemon, ichrome_logger as logger
    import re
    import json
    import time

    """Example for crawling a special background request."""

    # reset default logger level, such as DEBUG
    # import logging
    # logger.setLevel(logging.INFO)
    # launch the Chrome process and daemon process, will auto shutdown by 'with' expression.
    with ChromeDaemon(host="127.0.0.1", port=9222) as chromed:
        # create connection to Chrome Devtools
        chrome = Chrome(host="127.0.0.1", port=9222, timeout=3, retry=1)
        # now create a new tab without url
        tab = chrome.new_tab()
        # reset the url to bing.com, if loading time more than 5 seconds, will stop loading.
        # if inject js success, will alert Vue
        tab.set_url(
            "https://www.bing.com/", referrer="https://www.github.com/", timeout=5
        )
        # get_cookies from url
        logger.info(tab.get_cookies("http://cn.bing.com"))
        # test inject_js, if success, will alert jQuery version info 3.3.1
        logger.info(
            tab.inject_js("https://cdn.staticfile.org/jquery/3.3.1/jquery.min.js")
        )
        logger.info(tab.js("alert('jQuery inject success:' + jQuery.fn.jquery)"))
        tab.js(
            'alert("Check the links above disabled, and then input `test` to the input position.")'
        )
        # automate press accept for alert~
        tab.send("Page.handleJavaScriptDialog", accept=True)
        # remove href of the a tag.
        tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')")
        # remove href of all the 'a' tag.
        tab.querySelectorAll(
            "#sc_hdu>li>a", index=None, action="removeAttribute('href')"
        )
        # use querySelectorAll to get the elements.
        for i in tab.querySelectorAll("#sc_hdu>li"):
            logger.info(
                "Tag: %s, id:%s, class:%s, text:%s"
                % (i, i.get("id"), i.get("class"), i.text)
            )
        # enable the Network function, otherwise will not recv Network request/response.
        logger.info(tab.send("Network.enable"))
        # here will block until input string "test" in the input position.
        # tab is waiting for the event Network.responseReceived which accord with the given filter_function.
        recv_string = tab.wait_event(
            "Network.responseReceived",
            filter_function=lambda r: re.search("&\w+=test", r or ""),
            wait_seconds=None,
        )
        # now catching the "Network.responseReceived" event string, load the json.
        recv_string = json.loads(recv_string)
        # get the requestId to fetch its response body.
        request_id = recv_string["params"]["requestId"]
        logger.info("requestId: %s" % request_id)
        # send request for getResponseBody
        resp = tab.send("Network.getResponseBody", requestId=request_id, timeout=5)
        # now resp is the response body result.
        logger.info("getResponseBody success %s" % resp)
        # directly click the button matched the cssselector #sb_form_go, here is the submit button.
        logger.info(tab.click("#sb_form_go"))
        # show some html source code of the tab
        logger.info(tab.html[:100])
        # chromed.run_forever()


if __name__ == "__main__":
    example()

```

### Command Line Usage

```
λ python3 -m ichrome -s 9222
2018-11-27 23:01:59 DEBUG [ichrome] _base.py(329): kill chrome.exe --remote-debugging-port=9222
2018-11-27 23:02:00 DEBUG [ichrome] _base.py(329): kill chrome.exe --remote-debugging-port=9222

λ python3 -m ichrome -p 9222 --start_url "http://bing.com" --disable_image
2018-11-27 23:03:57 INFO  [ichrome] __main__.py(69): ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': 'localhost', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': True, 'start_url': 'http://bing.com', 'extra_config': '', 'max_deaths': 2, 'timeout': 2}
```

### TODO

- [ ] Concurrent support. (gevent, threading)

- [x] Add auto_restart while crash.

- [ ] Auto remove the zombie tabs with a lifebook.

- [ ] Add some useful examples.

- [ ] Coroutine support (for asyncio).
