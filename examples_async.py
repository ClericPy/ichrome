import asyncio
from typing import List

from ichrome import AsyncChromeDaemon
from ichrome.async_utils import Chrome, Tab, Tag, logger

logger.setLevel('DEBUG')
# Tab._log_all_recv = True
headless = False
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
    assert tabs1 == tabs2
    tab0: Tab = await chrome.get_tab(0)
    tab0_by_getitem = await chrome[0]
    assert tab0 == tab0_by_getitem
    assert tabs1[0] == tab0
    tab1: Tab = await chrome.new_tab()
    assert isinstance(tab1, Tab)
    await asyncio.sleep(0.2)
    await chrome.activate_tab(tab0)
    # test batch connect multiple tabs
    async with chrome.connect_tabs([tab0, tab1]):
        assert (await tab0.current_url) == 'about:blank'
        assert (await tab1.current_url) == 'about:blank'
        # watch the tabs switch
        await tab1.activate_tab()
        await asyncio.sleep(.2)
        await tab0.activate_tab()
        await asyncio.sleep(.2)
        await tab1.activate_tab()
    # test connect single tab
    async with chrome.connect_tabs(tab0):
        assert await tab0.current_url == 'about:blank'
    await chrome.close_tab(tab1)


async def test_tab_ws(tab: Tab):
    # test msg_id auto increase
    assert tab.msg_id == tab.msg_id - 1
    assert tab.status != 'connected'
    assert tab.ws is None
    async with tab():
        assert tab.ws
        assert tab.status == 'connected'
    # assert no connection out of async context.
    assert tab.ws is None
    assert tab.status != 'connected'


async def test_send_msg(tab: Tab):
    # test send msg
    assert tab.get_data_value(await tab.send('Network.enable'),
                              path='value',
                              default={}) == {}
    # disable Network
    await tab.disable('Network')


async def test_tab_cookies(tab: Tab):
    await tab.clear_browser_cookies()
    assert len(await tab.get_cookies(urls='http://python.org')) == 0
    assert await tab.set_cookie('test', 'test_value', url='http://python.org')
    assert await tab.set_cookie('test2', 'test_value', url='http://python.org')
    assert len(await tab.get_cookies(urls='http://python.org')) == 2
    assert await tab.delete_cookies('test', url='http://python.org')
    assert len(await tab.get_cookies(urls='http://python.org')) == 1
    # get all Browser cookies
    assert len(await tab.get_all_cookies()) > 0


async def test_tab_set_url(tab: Tab):
    # set new url for this tab, timeout will stop loading for timeout_stop_loading defaults to True
    assert await tab.set_url('http://python.org', timeout=5)


async def test_tab_js(tab: Tab):
    # test js update title
    await tab.js("document.title = 'abc'")
    new_title = await tab.current_title
    # test refresh_tab_info for tab meta info
    assert tab.title != new_title
    assert await tab.refresh_tab_info()
    assert tab.title == new_title
    # inject JS timeout return None
    assert (await tab.js('alert()', timeout=0.1)) is None
    # close the alert dialog
    assert await tab.handle_dialog(accept=True)
    # inject js url: vue.js
    # get window.Vue variable before injecting
    vue_obj = await tab.js('window.Vue')
    # {'id': 22, 'result': {'result': {'type': 'undefined'}}}
    assert 'undefined' in str(vue_obj)
    assert await tab.inject_js_url(
        'https://cdn.staticfile.org/vue/2.6.10/vue.min.js', timeout=3)
    vue_obj = await tab.js('window.Vue')
    # {'id': 23, 'result': {'result': {'type': 'function', 'className': 'Function', 'description': 'function wn(e){this._init(e)}', 'objectId': '{"injectedScriptId":1,"id":1}'}}}
    assert 'Function' in str(vue_obj)
    # querySelectorAll with JS, return list of Tag object
    tags = await tab.querySelectorAll('#id-search-field')
    assert tags, f'{[tags, type(tags)]}'
    assert isinstance(tags[0], Tag), f'{[tags[0], type(tags[0])]}'
    # querySelectorAll with JS, index arg is Not None, return Tag or None
    one_tag = await tab.querySelectorAll('#id-search-field', index=0)
    assert isinstance(one_tag, Tag)
    assert await tab.set_html('')
    assert (await tab.current_html) == '<html><head></head><body></body></html>'
    # reload the page
    assert await tab.reload()
    await tab.wait_loading(2)
    assert len(await tab.current_html) > 1000


async def test_wait_response(tab: Tab):
    # wait_response with filter_function
    # raw response: {'method': 'Network.responseReceived', 'params': {'requestId': '1000003000.69', 'loaderId': 'D7814CD633EDF3E699523AF0C4E9DB2C', 'timestamp': 207483.974238, 'type': 'Script', 'response': {'url': 'https://www.python.org/static/js/libs/masonry.pkgd.min.js', 'status': 200, 'statusText': '', 'headers': {'date': 'Sat, 05 Oct 2019 08:18:34 GMT', 'via': '1.1 vegur, 1.1 varnish, 1.1 varnish', 'last-modified': 'Tue, 24 Sep 2019 18:31:03 GMT', 'server': 'nginx', 'age': '290358', 'etag': '"5d8a60e7-6643"', 'x-served-by': 'cache-iad2137-IAD, cache-tyo19928-TYO', 'x-cache': 'HIT, HIT', 'content-type': 'application/x-javascript', 'status': '200', 'cache-control': 'max-age=604800, public', 'accept-ranges': 'bytes', 'x-timer': 'S1570263515.866582,VS0,VE0', 'content-length': '26179', 'x-cache-hits': '1, 170'}, 'mimeType': 'application/x-javascript', 'connectionReused': False, 'connectionId': 0, 'remoteIPAddress': '151.101.108.223', 'remotePort': 443, 'fromDiskCache': True, 'fromServiceWorker': False, 'fromPrefetchCache': False, 'encodedDataLength': 0, 'timing': {'requestTime': 207482.696803, 'proxyStart': -1, 'proxyEnd': -1, 'dnsStart': -1, 'dnsEnd': -1, 'connectStart': -1, 'connectEnd': -1, 'sslStart': -1, 'sslEnd': -1, 'workerStart': -1, 'workerReady': -1, 'sendStart': 0.079, 'sendEnd': 0.079, 'pushStart': 0, 'pushEnd': 0, 'receiveHeadersEnd': 0.836}, 'protocol': 'h2', 'securityState': 'unknown'}, 'frameId': 'A2971702DE69F008914F18EAE6514DD5'}}
    async def cb(request):
        result = ''
        if request:
            # wait_loading for ajax request
            result = await tab.get_response_body(request,
                                                 wait_loading=True,
                                                 timeout=5)
            ok = 'User-Agent' in result
            logger.warning(f'check wait_response callback, get_response {ok}')
            assert ok, f'{result} not contains "User-Agent"'
        else:
            raise ValueError(f'{request} is not True')

    # listening response
    def filter_function(r):
        ok = 'httpbin.org' in r['params']['response']['url']
        return print('get response url:', r['params']['response']['url'],
                     ok) or ok

    task = asyncio.ensure_future(
        tab.wait_response(filter_function=filter_function,
                          callback_function=cb,
                          timeout=10))
    await tab.set_url('http://httpbin.org/get')
    await tab.wait_loading(2)
    await task
    # click download link, without wait_loading.
    # request
    # {'method': 'Network.responseReceived', 'params': {'requestId': '2FAFC4FC410A6DEDE88553B1836C530B', 'loaderId': '2FAFC4FC410A6DEDE88553B1836C530B', 'timestamp': 212239.182469, 'type': 'Document', 'response': {'url': 'https://www.python.org/downloads/', 'status': 200, 'statusText': '', 'headers': {'status': '200', 'server': 'nginx', 'content-type': 'text/html; charset=utf-8', 'x-frame-options': 'DENY', 'cache-control': 'max-age=604800, public', 'via': '1.1 vegur\n1.1 varnish\n1.1 varnish', 'accept-ranges': 'bytes', 'date': 'Sat, 05 Oct 2019 10:51:48 GMT', 'age': '282488', 'x-served-by': 'cache-iad2139-IAD, cache-hnd18720-HND', 'x-cache': 'MISS, HIT', 'x-cache-hits': '0, 119', 'x-timer': 'S1570272708.444646,VS0,VE0', 'content-length': '113779'}, 'mimeType': 'text/html', 'connectionReused': False, 'connectionId': 0, 'remoteIPAddress': '123.23.54.43', 'remotePort': 443, 'fromDiskCache': True, 'fromServiceWorker': False, 'fromPrefetchCache': False, 'encodedDataLength': 0, 'timing': {'requestTime': 212239.179388, 'proxyStart': -1, 'proxyEnd': -1, 'dnsStart': -1, 'dnsEnd': -1, 'connectStart': -1, 'connectEnd': -1, 'sslStart': -1, 'sslEnd': -1, 'workerStart': -1, 'workerReady': -1, 'sendStart': 0.392, 'sendEnd': 0.392, 'pushStart': 0, 'pushEnd': 0, 'receiveHeadersEnd': 0.975}, 'protocol': 'h2', 'securityState': 'secure', 'securityDetails': {'protocol': 'TLS 1.2', 'keyExchange': 'ECDHE_RSA', 'keyExchangeGroup': 'X25519', 'cipher': 'AES_128_GCM', 'certificateId': 0, 'subjectName': 'www.python.org', 'sanList': ['www.python.org', 'docs.python.org', 'bugs.python.org', 'wiki.python.org', 'hg.python.org', 'mail.python.org', 'pypi.python.org', 'packaging.python.org', 'login.python.org', 'discuss.python.org', 'us.pycon.org', 'pypi.io', 'docs.pypi.io', 'pypi.org', 'docs.pypi.org', 'donate.pypi.org', 'devguide.python.org', 'www.bugs.python.org', 'python.org'], 'issuer': 'DigiCert SHA2 Extended Validation Server CA', 'validFrom': 1537228800, 'validTo': 1602676800, 'signedCertificateTimestampList': [], 'certificateTransparencyCompliance': 'unknown'}}, 'frameId': '882CFDEEA07EB00A5E7510ADD2A39F22'}}
    # response
    # {'id': 30, 'result': {'body': '<!doctype html>\n<!--[if lt IE 7]>   <html class="no-js ie6 lt-ie...', 'base64Encoded': False}}


async def test_tab_js_onload(tab: Tab):
    # add js onload
    js_id = await tab.add_js_onload(source='window.title=123456789')
    assert js_id
    await tab.set_url('http://p.3.cn')
    assert (await tab.get_variable('window.title')) == 123456789
    # remove js onload
    assert await tab.remove_js_onload(js_id)
    await tab.set_url('http://p.3.cn')
    assert (await tab.get_variable('window.title')) != 123456789


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
    rect = await tab.get_bounding_client_rect('[type="email"]')
    await tab.mouse_click(rect['left'], rect['top'], count=1)
    await tab.keyboard_send(text='1')
    await tab.keyboard_send(text='2')
    await tab.keyboard_send(text='3')
    await tab.mouse_click(rect['left'], rect['top'], count=2)
    selection = await tab.get_variable('window.getSelection().toString()')
    assert selection == '123'
    # test mouse_drag_rel_chain draw a square, sometime witeboard load failed.....
    await tab.set_url('https://zhoushuo.me/drawingborad/', timeout=5)
    await tab.mouse_click(5, 5)
    # drag with moving mouse, released on each `await`
    walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
        0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
    await walker.move(50 * 1.414, 50 * 1.414, 0.2)


async def test_examples():

    def on_startup(chromed):
        chromed.started = 1

    def on_shutdown(chromed):
        chromed.__class__.bye = 1

    async with AsyncChromeDaemon(headless=headless,
                                 on_startup=on_startup,
                                 on_shutdown=on_shutdown) as chromed:
        # test on_startup
        assert chromed.started
        # ===================== Chrome Test Cases =====================
        async with Chrome() as chrome:
            await test_chrome(chrome)
            # ===================== Tab Test Cases =====================
            tab: Tab = await chrome.new_tab()
            await test_tab_ws(tab)
            # same as: async with tab.connect():
            async with tab():
                # test send raw message
                await test_send_msg(tab)
                # test cookies operations
                await test_tab_cookies(tab)
                # set url
                await test_tab_set_url(tab)
                # test js
                await test_tab_js(tab)
                # test wait_response
                await test_wait_response(tab)
                # test add_js_onload remove_js_onload
                await test_tab_js_onload(tab)
                # test set ua and set headers
                await test_tab_set_ua_headers(tab)
                # load url for other tests
                await tab.set_url('http://httpbin.org/forms/post')
                # test current_html
                await test_tab_current_html(tab)
                # test screenshot
                await test_tab_screenshot(tab)
                # test double click some positions. test keyboard_send input
                await test_tab_keyboard_mouse(tab)
                # clear cache
                assert await tab.clear_browser_cache()
                # close tab
                await tab.close()
            # close_browser gracefully, I have no more need of chrome instance
            await chrome.close_browser()
            # await chrome.kill()
            sep = f'\n{"=" * 80}\n'
            logger.critical(
                f'{sep}Congratulations, all test cases passed.{sep}')
    assert AsyncChromeDaemon.bye


if __name__ == "__main__":
    asyncio.run(test_examples())
