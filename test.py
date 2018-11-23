from ichrome import Chrome, Tab, ChromeDaemon

import time


def example():
    with ChromeDaemon() as chromed:
        chromed.run_forever(0)
        chrome = Chrome()
        tab = chrome.new_tab()
        time.sleep(3)
        tab.close()
        


if __name__ == "__main__":
    example()
