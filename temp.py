from ichrome.async_utils import Chrome, logger
import asyncio
import os


async def test():
    logger.setLevel('DEBUG')
    chrome = Chrome()

    async def test_chrome_utils():
        # http connect to chrome.server.
        # [connected] <Chrome(connected): http://127.0.0.1:9222>.
        assert await chrome.connect()
        # [{'description': '', 'devtoolsFrontendUrl': '/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4', 'id': '30C16F9165C525A4002E827EDABD48A4', 'title': 'about:blank', 'type': 'page', 'url': 'about:blank', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/30C16F9165C525A4002E827EDABD48A4'}]
        version = await chrome.get_version()
        logger.info(f'version: {version}')
        assert version == await chrome.version
        os._exit(1)
        tab = await chrome.new_tab()
        assert tab
        assert tab.url == 'about:blank'
        assert await tab.refresh_tab_info()
        await asyncio.sleep(1)
        assert await tab.activate_tab()

    await test_chrome_utils()
    tabs = await chrome.tabs
    assert tabs
    # async with tab.connect:
    async with tabs[0](), tabs[1].connect:
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
        assert await tabs[1].close()
    # assert await tab.close_tab()
    # assert await chrome.close_tabs()


if __name__ == "__main__":
    asyncio.run(test())
