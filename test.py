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
