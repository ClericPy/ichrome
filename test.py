def example():
    from ichrome import Chrome, Tab, ChromeDaemon, ichrome_logger
    import re
    import json
    import time

    """Example for crawling a special background request."""

    # reset default logger level, such as DEBUG
    # import logging
    # ichrome_logger.setLevel(logging.INFO)
    # launch the Chrome process and daemon process, will auto shutdown by 'with' expression.
    with ChromeDaemon(host="127.0.0.1", port=9222) as chromed:
        # create connection to Chrome Devtools
        chrome = Chrome(host="127.0.0.1", port=9222, timeout=3, retry=1)
        # now create a new tab without url
        tab = chrome.new_tab()
        # reset the url to bing.com, if loading time more than 5 seconds, will stop loading.
        # test inject js file

        # if inject js success, will alert Vue
        tab.set_url("https://www.bing.com/", timeout=5)
        # test inject_js, if success, will alert jQuery version info 3.3.1
        ichrome_logger.info(
            tab.inject_js("https://cdn.staticfile.org/jquery/3.3.1/jquery.min.js")
        )
        ichrome_logger.info(
            tab.js("alert('jQuery inject success:' + jQuery.fn.jquery)")
        )
        tab.js('alert("Now input `test` to the input position.")')
        # enable the Network function, otherwise will not recv Network request/response.
        ichrome_logger.info(tab.send("Network.enable"))
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
        ichrome_logger.info("requestId: %s" % request_id)
        # send request for getResponseBody
        resp = tab.send("Network.getResponseBody", requestId=request_id, timeout=5)
        # now resp is the response body result.
        ichrome_logger.info("getResponseBody success %s" % resp)
        # directly click the button matched the cssselector #sb_form_go, here is the submit button.
        ichrome_logger.info(tab.click("#sb_form_go"))
        chromed.run_forever()


if __name__ == "__main__":
    example()
