from ichrome import Chrome, Tab, ChromeDaemon, ichrome_logger
import time

with ChromeDaemon():
    chrome = Chrome()
    tab = chrome[0]
    tab.set_url("http://cn.bing.com")
    for i in tab.querySelectorAll("#sc_hdu>li"):
        print(i, i.get("id"), i.text)
