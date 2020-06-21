# -*- coding: utf-8 -*-
"""
iChrome common use cases.
"""


def network_sniffer():
    """network flow sniffer

        0. launch a chrome daemon before running this use case
            > python3 -m ichrome
        1. run the function.
        2. change url of chrome's tab.
        3. watch the console logs.
    """
    import asyncio
    from ichrome import AsyncChrome, AsyncTab
    import json

    get_data_value = AsyncTab.get_data_value

    def filter_function(r):
        req = json.dumps(get_data_value(r, 'params.request'),
                         ensure_ascii=0,
                         indent=2)
        req_type = get_data_value(r, 'params.type')
        req_type = get_data_value(r, 'params.type')
        doc_url = get_data_value(r, 'params.documentURL')
        print(f'{doc_url} - {req_type}\n{req}', end=f'\n{"="*40}\n')
        # print(r)

    async def main():
        # listen network flow in 60 s
        timeout = 60
        async with AsyncChrome() as chrome:
            async with chrome.connect_tab(0) as tab:
                await tab.wait_request(filter_function=filter_function,
                                       timeout=timeout)

    asyncio.run(main())


def html_headless_crawler():
    """crawl a page with headless chrome"""
    import asyncio
    import re

    from ichrome import AsyncChrome, AsyncTab, AsyncChromeDaemon

    # WARNING: Chrome has a limit of 6 connections per host name, and a max of 10 connections.
    # Read more: https://blog.bluetriangle.com/blocking-web-performance-villain
    test_urls = ['http://httpbin.org/html'] * 3

    async def main():
        # crawl 3 urls in 3 tabs
        timeout = 3

        async def crawl(url):
            async with chrome.connect_tab(url, True) as tab:
                await tab.wait_loading(timeout=timeout)
                html = await tab.html
                result = re.search('<h1>(.*?)</h1>', html).group(1)
                print(result)
                assert result == 'Herman Melville - Moby-Dick'

        async with AsyncChromeDaemon(headless=True):
            async with AsyncChrome() as chrome:
                tasks = [asyncio.ensure_future(crawl(url)) for url in test_urls]
                await asyncio.wait(tasks)
                # await asyncio.sleep(2)

    asyncio.run(main())


def custom_ua_headless_crawler():
    """crawl a page with headless chrome"""
    import asyncio
    import re

    from ichrome import AsyncChrome, AsyncTab, AsyncChromeDaemon

    # WARNING: Chrome has a limit of 6 connections per host name, and a max of 10 connections.
    # Read more: https://blog.bluetriangle.com/blocking-web-performance-villain
    test_url = 'http://httpbin.org/user-agent'

    async def main():
        # crawl url with custom UA
        timeout = 3

        async with AsyncChromeDaemon(headless=True, user_agent='no UA'):
            async with AsyncChrome() as chrome:
                async with (await chrome[0])() as tab:
                    tab: AsyncTab
                    await tab.set_url(test_url, timeout=timeout)
                    html = await tab.html
                    result = re.search('("user-agent".*)', html).group(1)
                    print(result)
                    assert result == '"user-agent": "no UA"'

    asyncio.run(main())


if __name__ == "__main__":
    pass
    # network_sniffer()
    # html_headless_crawler()
    # custom_ua_headless_crawler()
