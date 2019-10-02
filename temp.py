from ichrome.async_utils import Chrome
import asyncio


async def test():
    chrome = Chrome()
    assert await chrome.connect()
    assert await chrome.get_version()
    assert await chrome.version
    assert await chrome.new_tab()
    tabs = await chrome.tabs
    assert tabs
    tab = tabs[0]
    assert tab.title == 'about:blank'
    assert await tab.refresh()
    await asyncio.sleep(1)
    assert await tab.activate_tab()


    await asyncio.sleep(1)
    assert await tab.close_tab()
    # assert await chrome.close_tabs()



if __name__ == "__main__":
    asyncio.run(test())
