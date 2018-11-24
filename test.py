from ichrome import Chrome, Tab, ChromeDaemon

import time


def example():
    with ChromeDaemon() as chromed:
        chrome = Chrome()
        tab = chrome.new_tab()
        tab.set_url("http://p.3.cn")
        print(tab.get_html()[:30])
        tab.js("alert('test js alert.')")
        time.sleep(3)
        tab.close()


if __name__ == "__main__":
    example()
