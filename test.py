from ichrome import Chrome, Tab, ChromeDaemon

import time
import json
from torequests.utils import print_info
import re


def example2():
    from ichrome import ichrome_logger
    import logging

    # ichrome_logger.setLevel(logging.DEBUG)
    with ChromeDaemon() as chromed:
        chrome = Chrome()
        tab = chrome.new_tab("http://p.3.cn")
        tab.set_url("https://www.bing.com/")
        print_info(tab.send("Network.enable"))
        # here will block until input `test` in the baidu input position.
        recv_string = tab.wait_event(
            "Network.responseReceived",
            filter_function=lambda r: re.search("&\w+=test", r or ""),
            wait_seconds=9999,
        )
        recv_string = json.loads(recv_string)
        rid = recv_string["params"]["requestId"]
        print_info("requestId: %s" % rid)
        a = tab.send("Network.getResponseBody", requestId=rid, timeout=5)
        print_info(a, "getResponseBody success")
        # chromed.run_forever()


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
    # example()
    example2()
