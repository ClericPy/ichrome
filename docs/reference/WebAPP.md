# Reference

```python
# ======================= server code ===========================

import uvicorn
from fastapi import FastAPI

from ichrome import AsyncTab
from ichrome.routers.fastapi_routes import ChromeAPIRouter

app = FastAPI()
# reset max_msg_size and window size for a large size screenshot
AsyncTab._DEFAULT_WS_KWARGS["max_msg_size"] = 10 * 1024**2
app.include_router(
    ChromeAPIRouter(headless=True, extra_config=["--window-size=1920,1080"]),
    prefix="/chrome",
)

uvicorn.run(app, port=8009)

# view url with your browser
# http://127.0.0.1:8009/chrome/screenshot?url=http://bing.com
# http://127.0.0.1:8009/chrome/download?url=http://bing.com

# ======================= client code ===========================

from inspect import getsource

import requests


# 1. request_get demo
print(
    requests.get(
        "http://127.0.0.1:8009/chrome/request_get",
        params={
            "__url": "http://httpbin.org/get?a=1",  # [required] target URL
            "__proxy": "http://127.0.0.1:1080",  # [optional]
            "__timeout": "10",  # [optional]
            "my_query": "OK",  # [optional] params for target URL
        },
        # headers for target URL
        headers={
            "User-Agent": "OK",
            "my_header": "OK",
            "Cookie": "my_cookie1=OK",
        },
        # cookies={"my_cookie2": "OK"}, # [optional] cookies for target URL if headers["Cookie"] is None
    ).text,
    flush=True,
)
# <html><head><meta name="color-scheme" content="light dark"></head><body><pre style="word-wrap: break-word; white-space: pre-wrap;">{
#   "args": {
#     "my_query": "OK"
#   },
#   "headers": {
#     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
#     "Accept-Encoding": "gzip, deflate",
#     "Cookie": "my_cookie1=OK",
#     "Host": "httpbin.org",
#     "My-Header": "OK",
#     "Upgrade-Insecure-Requests": "1",
#     "User-Agent": "OK",
#     "X-Amzn-Trace-Id": "Root=1-654d0157-04ab908a3779add762b164e3"
#   },
#   "origin": "0.0.0.0",
#   "url": "http://httpbin.org/get?my_query=OK"
# }
# </pre></body></html>


# 2. test tab_callback
async def tab_callback(self, tab, data, timeout):
    await tab.set_url(data["url"], timeout=timeout)
    return (await tab.querySelector("h1")).text


r = requests.post(
    "http://127.0.0.1:8009/chrome/do",
    json={
        "data": {"url": "http://httpbin.org/html"},
        "tab_callback": getsource(tab_callback),
        "timeout": 10,
    },
)
print(repr(r.text), flush=True)
'"Herman Melville - Moby-Dick"'


async def tab_callback(task, tab, data, timeout):
    await tab.wait_loading(3)
    return await tab.html


# 3. incognito_args demo
print(
    requests.post(
        "http://127.0.0.1:8009/chrome/do",
        json={
            "tab_callback": getsource(tab_callback),
            "timeout": 10,
            "incognito_args": {
                "url": "http://httpbin.org/ip",
                "proxyServer": "http://127.0.0.1:1080",
            },
        },
    ).text
)
# "<html><head><meta name=\"color-scheme\" content=\"light dark\"></head><body><pre style=\"word-wrap: break-word; white-space: pre-wrap;\">{\n  \"origin\": \"103.171.177.94\"\n}\n</pre></body></html>"


```
