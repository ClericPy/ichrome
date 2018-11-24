from ichrome import Chrome, Tab, ChromeDaemon

import time
import json
from torequests.utils import print_info


def example2():
    with ChromeDaemon() as chromed:
        chrome = Chrome()
        tab = chrome.new_tab()
        tab.set_url("http://baidu.com")
        print(tab.send("Network.enable"))
        recv_string = tab.recv({"method": "Network.responseReceived"})
        recv_string = json.loads(recv_string)
        rid = recv_string["params"]["requestId"]
        tab.send(
            "Network.getResponseBody", requestId=rid, callback=lambda r: print(r, "getResponseBody ok")
        )
        chromed.run_forever()


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
    #     example()
    example2()
