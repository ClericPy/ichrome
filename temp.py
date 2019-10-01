from ichrome.async_utils import Chrome
import asyncio


async def test():
    chrome = Chrome()
    assert await chrome.connect()
    print(await chrome.tabs())


if __name__ == "__main__":
    asyncio.run(test())
