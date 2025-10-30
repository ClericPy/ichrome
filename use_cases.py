# -*- coding: utf-8 -*-
"""
iChrome common use cases.
"""

import asyncio
import re

from ichrome import AsyncChrome, AsyncChromeDaemon


async def network_sniffer():
    """network flow sniffer"""

    async with AsyncChromeDaemon(headless=True) as cd:
        async with cd.connect_tab(0) as tab:
            stop_sig = asyncio.Future()

            async def cb(event, tab, buffer):
                print(
                    "Event:",
                    event["method"],
                    "Tab ID:URL:",
                    event["params"].get("request", {}).get("url"),
                )
                await buffer.continueRequest(event)
                # get response body
                response = await f.get_response(event, timeout=5)
                if response:
                    print("response body:", response["data"])
                else:
                    print("No response body")
                stop_sig.set_result(True)

            async with (
                tab.iter_fetch(
                    patterns=[
                        {
                            "urlPattern": "*myip.ipip.net*",  # wildcard pattern to filter requests
                            "requestStage": "Response",  # can be "Request" or "Response", response means to intercept after response headers received
                        },
                    ],
                    callback=cb,
                ) as f
            ):
                await tab.goto("https://myip.ipip.net/", timeout=0)
                async for _ in f:
                    if not stop_sig.done():
                        continue


async def html_headless_crawler():
    """crawl a page with headless chrome"""

    # WARNING: Chrome has a limit of 6 connections per host name, and a max of 10 connections.
    # Read more: https://blog.bluetriangle.com/blocking-web-performance-villain
    print(*AsyncChromeDaemon._iter_chrome_path())

    # crawl 3 urls in 3 tabs
    async def crawl(url):
        async with chrome.connect_tab(url, auto_close=True) as tab:
            print(f"Crawling: {url}", tab.id)
            await tab.wait_loading(timeout=10)
            return await tab.html

    # multi-urls concurrently crawl
    test_urls = [f"http://httpbin.org/get?a={i}" for i in range(2)]
    async with AsyncChromeDaemon(headless=True):
        async with AsyncChrome() as chrome:
            tasks = [asyncio.ensure_future(crawl(url)) for url in test_urls]
            for task in asyncio.as_completed(tasks):
                html = await task
                match = re.search(r'"url": "([^"]+)"', html)
                if match:
                    print("Crawled:", match.group(1))
                else:
                    print("Crawled: Unknown URL")
    # Crawling: http://httpbin.org/get?a=0 E32C6001BEA62446E70A0CD187B9F9CB
    # Crawling: http://httpbin.org/get?a=1 5D1C7C80265BE7CBCBD0A9BEF75A4EB7
    # Crawled: https://httpbin.org/get?a=1
    # Crawled: https://httpbin.org/get?a=0


async def use_proxy():
    async with AsyncChromeDaemon(headless=True) as cd:
        # create a new tab
        async with cd.connect_tab(index=None) as tab:
            await tab.goto("https://myip.ipip.net/", timeout=5)
            print(await tab.html)
        # Privacy Mode, proxyServer arg maybe not work on Chrome, for `Target.createBrowserContext` is the EXPERIMENTAL feature(but chromium is ok).
        # https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-createBrowserContext
        # Linux and MacOS may work well.
        async with cd.incognito_tab(proxyServer="http://127.0.0.1:8080") as tab:
            await tab.goto("https://myip.ipip.net/", timeout=5)
            print(await tab.html)


if __name__ == "__main__":
    pass
    # asyncio.run(network_sniffer())
    # asyncio.run(html_headless_crawler())
    # asyncio.run(use_proxy())
