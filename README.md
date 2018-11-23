# ichrome - v0.0.1

> A toy for using chrome under the [Chrome Devtools Protocol(CDP)](https://chromedevtools.github.io/devtools-protocol/). For python3.6+ (who care python2.x).



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


### TODO

- Concurrent support.

- Add auto_restart while crash.

- Auto-remove the zombie tabs with a lifebook.

- Add some useful examples.

- Refactor for asyncio.
