# ichrome - v0.0.2

> A toy for using chrome under the [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/). For python3.6+ (who care python2.x).

## Install

> pip install ichrome -U

## Why?

- pyppeteer/selenium is awesome, but I don't need so much...


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
from ichrome import Chrome, Tab, ChromeDaemon
from ichrome import ichrome_logger
"""Crawling a special background request."""

# reset default logger level, such as DEBUG
# import logging
# ichrome_logger.setLevel(logging.INFO)
# launch the Chrome process and daemon process, will auto shutdown by 'with' expression.
with ChromeDaemon(host="127.0.0.1", port=9222):
    # create connection to Chrome Devtools
    chrome = Chrome(host="127.0.0.1", port=9222, timeout=3, retry=1)
    # now create a new tab without url
    tab = chrome.new_tab()
    # reset the url to bing.com, if loading time more than 5 seconds, will stop loading.
    tab.set_url("https://www.bing.com/", timeout=5)
    # enable the Network function, otherwise will not recv Network request/response.
    ichrome_logger.info(tab.send("Network.enable"))
    # here will block until input string "test" in the input position.
    # tab is waiting for the event Network.responseReceived which accord with the given filter_function.
    recv_string = tab.wait_event(
        "Network.responseReceived",
        filter_function=lambda r: re.search("&\w+=test", r or ""),
        wait_seconds=9999,
    )
    # now catching the "Network.responseReceived" event string, load the json.
    recv_string = json.loads(recv_string)
    # get the requestId to fetch its response body.
    request_id = recv_string["params"]["requestId"]
    ichrome_logger.info("requestId: %s" % request_id)
    # send request for getResponseBody
    resp = tab.send("Network.getResponseBody", requestId=request_id, timeout=5)
    # now resp is the response body result.
    ichrome_logger.info("getResponseBody success %s"% resp)


```

### TODO

- [ ] Concurrent support. (gevent, threading)

- [x] Add auto_restart while crash.

- [ ] Auto remove the zombie tabs with a lifebook.

- [ ] Add some useful examples.

- [ ] Coroutine support (for asyncio).
