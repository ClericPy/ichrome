from ichrome import Chrome, Tab, ChromeDaemon, ichrome_logger
import time

with ChromeDaemon():
    chrome = Chrome()
    tab = chrome[0]
    tab.set_url("http://cn.bing.com")
    print(tab.querySelectorAll("#sc_hdu>li>a", index=2, action="text").result)
