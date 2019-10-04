from ichrome.async_utils import Chrome, logger
import asyncio


async def test():
    logger.setLevel('DEBUG')
    chrome = Chrome()
    assert await chrome.connect()

    async def test_chrome_utils():
        # http connect to chrome.server.
        # [connected] <Chrome(connected): http://127.0.0.1:9222>.
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        version = await chrome.get_version()
        logger.info(f'version: {version}')
        assert version == await chrome.version
        tab = await chrome.new_tab()
        assert tab.url == 'about:blank'
        assert await tab.refresh_tab_info()
        await asyncio.sleep(1)
        for tab in await chrome.tabs:
            # await chrome.activate_tab(tab)
            await tab.activate_tab()
            await asyncio.sleep(0.5)
        for index, tab in enumerate(await chrome.tabs):
            if index > 0:
                await tab.close_tab()

    async def test_tab_utils():
        for _ in range(2):
            await chrome.new_tab()
        await asyncio.sleep(1)
        tabs = await chrome.tabs
        # async with tab.connect:
        # 2 ways to connect ws: 1. tab(); 2. tab.connect
        async with chrome.connect_tabs(tabs):
            for _ in range(2):
                # tabs will be activated
                await tabs[0].activate()
                await asyncio.sleep(1)
                await tabs[1].activate()
                await asyncio.sleep(1)

            # assert await tabs[1].send('Page.enable', timeout=0) is None
            # resp = await tabs[1].send('Page.enable')
            # assert resp == '{"id":2,"result":{}}'

            # await asyncio.sleep(3)
            # assert await tabs[1].activate()
            print(await tabs[1].close())
        # assert await tab.close_tab()
        # assert await chrome.close_tabs()

    async def test_tab_utils2():
        tab = await chrome.new_tab('http://bing.com')
        async with tab():
            await tab.wait_loading(3)
            print(await tab.current_url)
            html = await tab.html
            print(html[:100])

    # await test_chrome_utils()
    # await test_tab_utils()
    await test_tab_utils2()


if __name__ == "__main__":
    asyncio.run(test())
