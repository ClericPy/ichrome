import asyncio
import json

from ichrome import AsyncChromeDaemon


async def main():
    async with AsyncChromeDaemon(clear_after_shutdown=True,
                                 headless=False,
                                 disable_image=False,
                                 user_data_dir='./ichrome_user_data') as cd:
        async with cd.connect_tab(0, auto_close=True) as tab:
            loaded = await tab.goto('https://httpbin.org/forms/post',
                                    timeout=10)
            html = await tab.html
            title = await tab.title
            print(
                f'page loaded ok: {loaded}, HTML length is {len(html)}, title is "{title}"'
            )
            # try setting the input tag value with JS
            await tab.js(
                r'''document.querySelector('[value="bacon"]').checked = true''')
            # or you can click the checkbox
            await tab.click('[value="cheese"]')
            # you can set the value of input
            await tab.js(
                r'''document.querySelector('[name="custname"]').value = "1234"'''
            )
            # now click the submit button
            await tab.click('form button')
            await tab.wait_loading(5)
            # extract the JSON with regex
            result = await tab.findone(r'<pre.*?>([\s\S]*?)</pre>')
            print(json.loads(result))
            # ================= now tab will be closed, and cache will be clear =================
            # try debugging with repl mode like: tab.url
            # from ichrome import repl; await repl()


if __name__ == "__main__":
    asyncio.run(main())
