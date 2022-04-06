import asyncio
from pathlib import Path
from typing import List

from ichrome import AsyncChromeDaemon, ChromeEngine
from ichrome.async_utils import AsyncTab, Chrome, Tab, Tag, logger

# logger.setLevel('DEBUG')
# Tab._log_all_recv = True
# headless = False
headless = True


async def test_chrome(chrome: Chrome):
    assert str(chrome) == '<Chrome(connected): http://127.0.0.1:9222>'
    assert chrome.server == 'http://127.0.0.1:9222'
    version = await chrome.version
    assert isinstance(version, dict) and 'Browser' in version
    ok = await chrome.check()
    assert ok is True
    ok = await chrome.ok
    assert ok is True
    resp = await chrome.get_server('json')
    assert isinstance(resp.json(), list)
    tabs1: List[Tab] = await chrome.get_tabs()
    tabs2: List[Tab] = await chrome.tabs
    assert tabs1 == tabs2 and tabs1 and tabs2, (tabs1, tabs2)
    tab0: Tab = await chrome.get_tab(0)
    tab0_by_getitem = await chrome[0]
    assert tab0 == tab0_by_getitem
    assert tabs1 == [tab0], (tabs1, tab0)
    tab1: Tab = await chrome.new_tab()
    assert isinstance(tab1, Tab)
    await asyncio.sleep(0.2)
    await chrome.activate_tab(tab0)
    # test batch connect multiple tabs
    async with chrome.connect_tabs([tab0, tab1]):
        assert tab0.status == 'connected', (tab0.status, tab0)
        assert tab1.status == 'connected', (tab1.status, tab1)
        # watch the tabs switch
        await tab1.activate_tab()
        await asyncio.sleep(.2)
        await tab0.activate_tab()
        await asyncio.sleep(.2)
        await tab1.activate_tab()
    # test connect single tab
    async with chrome.connect_tabs(tab0):
        assert tab0.status == 'connected'
    await chrome.close_tab(tab1)


async def test_tab_ws(tab: Tab):
    # test msg_id auto increase
    assert tab.msg_id == tab.msg_id - 1
    assert tab.status == 'disconnected', tab.status
    assert tab.ws is None or (tab.flatten and not tab._session_id)
    async with tab():
        assert tab.ws
        assert tab.status == 'connected'
    # assert no connection out of async context.
    assert tab.status == 'disconnected'
    assert tab.ws is None or (tab.flatten and not tab._session_id)


async def test_send_msg(tab: Tab):
    # test send msg
    assert tab.get_data_value(await tab.send('Network.enable'),
                              value_path='value',
                              default={}) == {}
    # disable Network
    await tab.disable('Network')


async def test_tab_cookies(tab: Tab):
    await tab.clear_browser_cookies()
    assert len(await tab.get_cookies(urls='http://httpbin.org/get')) == 0
    assert await tab.set_cookie('test', 'test_value', url='https://github.com/')
    assert await tab.set_cookie('test2',
                                'test_value',
                                url='https://github.com/')
    assert await tab.set_cookies([{
        'name': 'a',
        'value': 'b',
        'url': 'http://httpbin.org/get'
    }])
    assert len(await tab.get_cookies(urls='https://github.com/')) == 2
    assert len(await tab.get_cookies(urls='http://httpbin.org/get')) == 1
    assert await tab.delete_cookies('test', url='https://github.com/')
    assert len(await tab.get_cookies(urls='https://github.com/')) == 1
    # get all Browser cookies
    assert len(await tab.get_all_cookies()) > 0


async def test_browser_context(tab1: Tab, chrome: Chrome,
                               chromed: AsyncChromeDaemon):
    # test chrome.create_context
    assert len(await tab1.get_all_cookies()) > 0
    async with chrome.create_context(proxyServer=None) as context:
        async with context.new_tab() as tab:
            assert len(await tab.get_all_cookies()) == 0
            await tab.set_cookie('a', '1', 'http://httpbin.org')
            assert len(await tab.get_all_cookies()) > 0

    # test chrome_daemon.create_context
    assert len(await tab1.get_all_cookies()) > 0
    async with chromed.create_context(proxyServer=None) as context:
        async with context.new_tab() as tab:
            assert len(await tab.get_all_cookies()) == 0
            await tab.set_cookie('a', '1', 'http://httpbin.org')
            assert len(await tab.get_all_cookies()) > 0

    # test chrome.incognito_tab
    assert len(await tab1.get_all_cookies()) > 0
    async with chrome.incognito_tab(proxyServer=None) as tab:
        assert len(await tab.get_all_cookies()) == 0
        await tab.set_cookie('a', '1', 'http://httpbin.org')
        assert len(await tab.get_all_cookies()) > 0

    # test chrome_daemon.incognito_tab
    assert len(await tab1.get_all_cookies()) > 0
    async with chromed.incognito_tab(proxyServer=None) as tab:
        assert len(await tab.get_all_cookies()) == 0
        await tab.set_cookie('a', '1', 'http://httpbin.org')
        assert len(await tab.get_all_cookies()) > 0


async def test_tab_set_url(tab: Tab):
    # set new url for this tab, timeout will stop loading for timeout_stop_loading defaults to True
    assert not (await tab.set_url('http://httpbin.org/delay/5', timeout=2))
    assert await tab.set_url('http://httpbin.org/delay/0', timeout=3)
    await tab.goto('https://httpbin.org/forms/post')
    assert await tab.wait_tag(
        '[name="custemail"]',
        max_wait_time=10), 'wait_tag failed for [name="custemail"]'
    mhtml_len = len(await tab.snapshot_mhtml())
    assert mhtml_len in range(2273, 2300), f'test snapshot failed {mhtml_len}'


async def test_tab_js(tab: Tab):
    # test js update title
    await tab.js("document.title = 'abc'")
    # test js_code
    assert (await tab.js_code('return document.title')) == 'abc'
    # test findall
    await tab.js("document.title = 123456789")
    assert (await tab.findall('<title>(.*?)</title>')) == ['123456789']
    assert (await
            tab.findall('<title>.*?</title>')) == ['<title>123456789</title>']
    assert (await tab.findall('<title>(1)(2).*?</title>')) == [['1', '2']]
    assert (await tab.findall('<title>(1)(2).*?</title>', 'body')) == []
    new_title = await tab.current_title
    # test refresh_tab_info for tab meta info
    assert (await tab.title) == new_title
    assert tab._title != new_title
    assert await tab.refresh_tab_info()
    assert tab._title == new_title
    # inject JS timeout return None
    assert (await tab.js('alert()')) is None
    # close the alert dialog
    assert await tab.handle_dialog(accept=True)
    # inject js url: vue.js
    # get window.Vue variable before injecting
    vue_obj = await tab.js('window.Vue', 'result.result.type')
    # {'id': 22, 'result': {'result': {'type': 'undefined'}}}
    assert vue_obj == 'undefined'
    assert await tab.inject_js_url(
        'https://cdn.staticfile.org/vue/2.6.10/vue.min.js', timeout=3)
    vue_obj = await tab.js('window.Vue', value_path=None)
    # {'id': 23, 'result': {'result': {'type': 'function', 'className': 'Function', 'description': 'function wn(e){this._init(e)}', 'objectId': '{"injectedScriptId":1,"id":1}'}}}
    assert 'Function' in str(vue_obj)
    tag = await tab.querySelector('#not-exist')
    assert not tag
    # querySelectorAll with JS, return list of Tag object
    tags = await tab.querySelectorAll('label')
    assert tags, f'{[tags, type(tags)]}'
    assert isinstance(tags[0], Tag), f'{[tags[0], type(tags[0])]}'
    assert tags[0].tagName == 'label', f'{[tags[0], tags[0].tagName]}'
    # querySelectorAll with JS, index arg is Not None, return Tag or None
    one_tag = await tab.querySelectorAll('label', index=0)
    assert isinstance(one_tag, Tag)
    assert await tab.set_html('')
    assert (await tab.current_html) == '<html><head></head><body></body></html>'
    # reload the page
    assert await tab.reload()
    await tab.wait_loading(8)
    current_html = await tab.html
    assert len(current_html) > 100, current_html
    # test wait tags
    result = await tab.wait_tags('labels', max_wait_time=1)
    assert result == []
    assert await tab.wait_tag('label', max_wait_time=3)
    assert await tab.includes('Telephone')
    assert not (await tab.includes('python-ichrome'))
    assert await tab.wait_includes('Telephone')
    assert (await tab.wait_includes('python-ichrome', max_wait_time=1)) is False
    assert await tab.wait_findall('Telephone')
    assert (await tab.wait_findall('python-ichrome', max_wait_time=1)) == []
    # test wait_console_value
    await tab.js('setTimeout(() => {console.log(123)}, 2);')
    assert (await tab.wait_console_value()) == 123


async def test_wait_response(tab: Tab):
    # wait_response with filter_function
    # raw response: {'method': 'Network.responseReceived', 'params': {'requestId': '1000003000.69', 'loaderId': 'D7814CD633EDF3E699523AF0C4E9DB2C', 'timestamp': 207483.974238, 'type': 'Script', 'response': {'url': 'https://www.python.org/static/js/libs/masonry.pkgd.min.js', 'status': 200, 'statusText': '', 'headers': {'date': 'Sat, 05 Oct 2019 08:18:34 GMT', 'via': '1.1 vegur, 1.1 varnish, 1.1 varnish', 'last-modified': 'Tue, 24 Sep 2019 18:31:03 GMT', 'server': 'nginx', 'age': '290358', 'etag': '"5d8a60e7-6643"', 'x-served-by': 'cache-iad2137-IAD, cache-tyo19928-TYO', 'x-cache': 'HIT, HIT', 'content-type': 'application/x-javascript', 'status': '200', 'cache-control': 'max-age=604800, public', 'accept-ranges': 'bytes', 'x-timer': 'S1570263515.866582,VS0,VE0', 'content-length': '26179', 'x-cache-hits': '1, 170'}, 'mimeType': 'application/x-javascript', 'connectionReused': False, 'connectionId': 0, 'remoteIPAddress': '151.101.108.223', 'remotePort': 443, 'fromDiskCache': True, 'fromServiceWorker': False, 'fromPrefetchCache': False, 'encodedDataLength': 0, 'timing': {'requestTime': 207482.696803, 'proxyStart': -1, 'proxyEnd': -1, 'dnsStart': -1, 'dnsEnd': -1, 'connectStart': -1, 'connectEnd': -1, 'sslStart': -1, 'sslEnd': -1, 'workerStart': -1, 'workerReady': -1, 'sendStart': 0.079, 'sendEnd': 0.079, 'pushStart': 0, 'pushEnd': 0, 'receiveHeadersEnd': 0.836}, 'protocol': 'h2', 'securityState': 'unknown'}, 'frameId': 'A2971702DE69F008914F18EAE6514DD5'}}

    # listening response
    def filter_function(r):
        url = r['params']['response']['url']
        ok = 'httpbin.org' in url
        logger.warning('get response url: %s %s' % (url, ok))
        return ok

    task = asyncio.ensure_future(
        tab.wait_response(filter_function=filter_function,
                          response_body=True,
                          timeout=10))
    await tab.set_url('http://httpbin.org/get')
    result = await task
    ok = 'User-Agent' in result['data']
    logger.warning(f'check wait_response callback, get_response {ok}')
    assert ok, f'{result} not contains "User-Agent"'

    # test wait_response_context

    def filter_function2(r):
        try:
            url = r['params']['response']['url']
            return url == 'http://httpbin.org/get'
        except KeyError:
            pass

    async with tab.wait_response_context(filter_function=filter_function2,
                                         timeout=5) as r:
        await tab.goto('http://httpbin.org/get')
        result = (await r) or {}
        assert 'User-Agent' in result.get('data', ''), result


async def test_tab_js_onload(tab: Tab):
    # add js onload
    js_id = await tab.add_js_onload(source='window.title=123456789')
    assert js_id
    await tab.set_url('http://httpbin.org/get')
    assert (await tab.get_variable('window.title')) == 123456789
    # remove js onload
    assert await tab.remove_js_onload(js_id)
    await tab.set_url('http://httpbin.org/get')
    assert (await tab.get_variable('window.title')) != 123456789
    assert (await tab.get_variable('[1, 2, 3]')) != [1, 2, 3]
    assert (await tab.get_variable('[1, 2, 3]', jsonify=True)) == [1, 2, 3]
    current_url = await tab.current_url
    url = await tab.url
    assert url == 'http://httpbin.org/get' == current_url, url


async def test_tab_current_html(tab: Tab):
    html = await tab.get_html()
    assert 'Customer name:' in html
    # alias current_html
    assert html == (await tab.current_html) == (await tab.html)


async def test_tab_screenshot(tab: Tab):
    # screenshot
    screen = await tab.screenshot()
    part = await tab.screenshot_element('fieldset')
    assert screen
    assert part
    assert len(screen) > len(part)


async def test_tab_set_ua_headers(tab: Tab):
    # test set_ua
    await tab.set_ua('Test UA')
    # test set_headers
    await tab.set_headers({'A': '1', 'B': '2'})
    await tab.set_url('http://httpbin.org/get')
    html = await tab.get_html()
    assert '"A": "1"' in html and '"B": "2"' in html and '"User-Agent": "Test UA"' in html


async def test_tab_keyboard_mouse(tab: Tab):
    if 'httpbin.org/forms/post' not in (await tab.current_url):
        await tab.set_url('http://httpbin.org/forms/post', timeout=5)
    rect = await tab.get_bounding_client_rect('[type="tel"]')
    await tab.mouse_click(rect['left'], rect['top'], count=1)
    await tab.keyboard_send(text='1')
    await tab.keyboard_send(text='2')
    await tab.keyboard_send(text='3')
    await tab.keyboard_send(string='123')
    await tab.mouse_click(rect['left'], rect['top'], count=2)
    selection = await tab.get_variable('window.getSelection().toString()')
    assert selection == '123123'
    # test mouse_click_element
    await tab.mouse_click_element_rect('[type="tel"]')
    selection = await tab.get_variable('window.getSelection().toString()')
    assert selection == ''
    # test mouse_drag_rel_chain draw a square, sometime witeboard load failed.....
    await tab.set_url('https://zhoushuo.me/drawingborad/', timeout=5)
    await tab.mouse_click(5, 5)
    # drag with moving mouse, released on each `await`
    walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
        0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
    await walker.move(50 * 1.414, 50 * 1.414, 0.2)


async def test_iter_events(tab: Tab):
    async with tab.iter_events(['Page.loadEventFired'],
                               timeout=8) as events_iter:
        await tab.goto('http://httpbin.org/get', timeout=0)
        data = await events_iter
        assert data, data
    async with tab.iter_events(['Page.loadEventFired'],
                               timeout=8) as events_iter:
        await tab.goto('http://httpbin.org/get', timeout=0)
        data = await events_iter.get()
        assert data, data
    async with tab.iter_events(['Page.loadEventFired'],
                               timeout=8) as events_iter:
        await tab.goto('http://httpbin.org/get', timeout=0)
        async for data in events_iter:
            assert data
            break

    # test iter_fetch
    async with tab.iter_fetch(patterns=[{
            'urlPattern': '*httpbin.org/get?a=*'
    }]) as f:
        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        # test continueRequest
        await f.continueRequest(data)
        assert await tab.wait_includes('origin')

        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        # test modify response
        await f.fulfillRequest(data, 200, body=b'hello world.')
        assert await tab.wait_includes('hello world.')
        await tab.goto('http://httpbin.org/get?a=1', timeout=0)
        data = await f
        assert data
        await f.failRequest(data, 'AccessDenied')
        assert (await tab.url).startswith('chrome-error://')


async def test_init_tab(chromed: AsyncChromeDaemon):
    # test init tab from chromed, create new tab and auto_close=True
    async with chromed.connect_tab(index=None, auto_close=True) as tab:
        TEST_DRC_OK = False

        def test_drc(tab, data_dict):
            nonlocal TEST_DRC_OK
            TEST_DRC_OK = True

        tab.default_recv_callback.append(test_drc)
        await tab.goto("https://httpbin.org", timeout=5)
        title = await tab.current_title
        assert TEST_DRC_OK, 'test default_recv_callback failed'
        assert title == 'httpbin.org', title
        tab.default_recv_callback.clear()


async def test_fetch_context(tab: AsyncTab):
    async with tab.iter_fetch(patterns=[{
            'urlPattern': '*httpbin.org/ip*'
    }]) as f:
        await tab.goto('http://httpbin.org/ip', timeout=0)
        async for r in f:
            assert 'httpbin.org/ip' in r['params']['request']['url']
            await f.continueRequest(r)
            break


async def test_examples():

    def on_startup(chromed):
        chromed.started = 1

    def on_shutdown(chromed):
        chromed.__class__.bye = 1

    host = '127.0.0.1'
    port = 9222
    async with AsyncChromeDaemon(host=host,
                                 port=port,
                                 headless=headless,
                                 on_startup=on_startup,
                                 on_shutdown=on_shutdown,
                                 clear_after_shutdown=True) as chromed:
        await test_init_tab(chromed)
        logger.info('test init tab from chromed OK.')
        # test on_startup
        assert chromed.started
        logger.info('test on_startup OK.')
        # ===================== Chrome Test Cases =====================
        async with Chrome(host=host, port=port) as chrome:
            memory = chrome.get_memory()
            assert memory > 0
            logger.info('get_memory OK. (%s MB)' % memory)
            await test_chrome(chrome)
            logger.info('test_chrome OK.')
            # ===================== Tab Test Cases =====================
            # Duplicate, use async with chrome.connect_tab(None) instead
            tab: Tab = await chrome.new_tab()
            await test_tab_ws(tab)
            # same as: async with tab.connect():
            async with tab():
                # test send raw message
                await test_send_msg(tab)
                logger.info('test_send_msg OK.')
                # test cookies operations
                await test_tab_cookies(tab)
                logger.info('test_tab_cookies OK.')
                # test_browser_context
                await test_browser_context(tab, chrome, chromed)
                logger.info('test_browser_context OK.')
                # set url
                await test_tab_set_url(tab)
                logger.info('test_tab_set_url OK.')
                # test js
                await test_tab_js(tab)
                logger.info('test_tab_js OK.')
                # test wait_response
                await test_wait_response(tab)
                logger.info('test_wait_response OK.')
                # test fetch_context
                await test_fetch_context(tab)
                logger.info('test_fetch_context OK.')
                # test add_js_onload remove_js_onload
                await test_tab_js_onload(tab)
                logger.info('test_tab_js_onload OK.')
                # test iter_events iter_fetch
                await test_iter_events(tab)
                logger.info('test_iter_events OK.')
                # test set ua and set headers
                await test_tab_set_ua_headers(tab)
                logger.info('test_tab_set_ua_headers OK.')
                # load url for other tests
                await tab.set_url('http://httpbin.org/forms/post')
                # test current_html
                await test_tab_current_html(tab)
                logger.info('test_tab_current_html OK.')
                # test screenshot
                await test_tab_screenshot(tab)
                logger.info('test_tab_screenshot OK.')
                # test double click some positions. test keyboard_send input
                await test_tab_keyboard_mouse(tab)
                logger.info('test_tab_keyboard_mouse OK.')
                # clear cache
                assert await tab.clear_browser_cache()
                logger.info('clear_browser_cache OK.')
                # close tab
                await tab.close()
            # test chrome.connect_tab
            async with chrome.connect_tab(chrome.server + '/json', True) as tab:
                await tab.wait_loading(2)
                assert 'webSocketDebuggerUrl' in (await tab.current_html)
            logger.info('test connect_tab OK.')
            # close_browser gracefully, I have no more need of chrome instance
            await chrome.close_browser()
            # await chrome.kill()
            sep = f'\n{"=" * 80}\n'
            logger.critical(
                f'{sep}Congratulations, all test cases passed(flatten={Tab._DEFAULT_FLATTEN}).{sep}'
            )
    assert AsyncChromeDaemon.bye
    # test clear_after_shutdown
    _user_dir_path = AsyncChromeDaemon.DEFAULT_USER_DIR_PATH / 'chrome_9222'
    dir_cleared = not _user_dir_path.is_dir()
    assert dir_cleared


def test_chrome_engine():

    async def _test_chrome_engine():

        tab_callback1 = r'''async def tab_callback(self, tab, url, timeout):
            await tab.set_url(url, timeout=5)
            return 'Bing' in (await tab.title)'''

        async def tab_callback2(self, tab, url, timeout):
            await tab.set_url(url, timeout=5)
            return 'Bing' in (await tab.title)

        async with ChromeEngine(
                max_concurrent_tabs=5,
                headless=True,
                disable_image=True,
                after_shutdown=lambda cd: cd._clear_user_dir()) as ce:
            # test normal usage
            tasks = [
                asyncio.create_task(
                    ce.do('http://bing.com', tab_callback1, timeout=10))
                for _ in range(3)
            ] + [
                asyncio.create_task(
                    ce.do('http://bing.com', tab_callback2, timeout=10))
                for _ in range(3)
            ]
            for task in tasks:
                assert (await task) is True
            # test screenshot full screen and partial tag range.
            tasks = [
                asyncio.create_task(
                    ce.screenshot('http://bing.com', '#sbox', timeout=10)),
                asyncio.create_task(ce.screenshot('http://bing.com',
                                                  timeout=10))
            ]
            results = [await task for task in tasks]
            assert 1000 < len(results[0]) < len(results[1])

            # test download
            tasks = [
                asyncio.create_task(
                    ce.download('http://bing.com', '#sbox', timeout=10)),
                asyncio.create_task(ce.download('http://bing.com', timeout=10))
            ]
            results = [await task for task in tasks]
            assert 1000 < len(results[0]['tags'][0]) < len(results[1]['html'])

            # test connect_tab
            async with ce.connect_tab() as tab:
                await tab.goto('http://pypi.org')
                title = await tab.title
                assert 'PyPI' in title, title
        logger.critical('test_chrome_engine OK')
        _user_dir_path = AsyncChromeDaemon.DEFAULT_USER_DIR_PATH / f'chrome_{ChromeEngine.START_PORT}'
        dir_cleared = not _user_dir_path.is_dir()
        assert dir_cleared

    # asyncio.run will raise aiohttp issue: https://github.com/aio-libs/aiohttp/issues/4324
    asyncio.get_event_loop().run_until_complete(_test_chrome_engine())


def test_all():
    import time
    AsyncChromeDaemon.DEFAULT_USER_DIR_PATH = Path('./ichrome_user_data')
    for flatten in [True, False, True]:
        logger.critical('Start testing flatten=%s.' % flatten)
        Tab._DEFAULT_FLATTEN = flatten
        test_chrome_engine()
        time.sleep(1)
        asyncio.get_event_loop().run_until_complete(test_examples())
        time.sleep(1)


if __name__ == "__main__":
    test_all()
