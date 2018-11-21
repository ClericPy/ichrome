
from ichrome import ChromeDaemon


if __name__ == "__main__":
    chrome = ChromeDaemon(port=9222)
    chrome.run_forever()
