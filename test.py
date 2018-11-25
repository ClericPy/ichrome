import json
import re
import time

from ichrome import Chrome, ChromeDaemon, Tab
from torequests.utils import print_info


def example2():
    from ichrome import Chrome, Tab, ChromeDaemon
    from ichrome import ichrome_logger
    """Example for crawling a special background request."""

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
