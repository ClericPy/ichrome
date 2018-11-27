from ichrome import Chrome, Tab, ChromeDaemon, ichrome_logger
import time

with ChromeDaemon():
    chrome = Chrome()
    tab = chrome[0]
    tab.set_url("http://cn.bing.com")
    for i in tab.querySelectorAll("#sc_hdu>li"):
        ichrome_logger.info(
                "Tag: %s, id:%s, class:%s, text:%s"
                % (i, i.get("id"), i.get("class"), i.text)
            )