import time

from ichrome import AsyncTab
from ichrome.debugger import get_a_tab, network_sniffer, launch

# There are 3 ways to create a daemon
# 1. get_a_tab: auto find the existing Chrome (launched before like python -m ichrome), or create a new daemon
# 2. daemon = Daemon()
# 3. daemon = launch()

# type hints for autocomplete in the IDE
daemon = launch()
tab: AsyncTab = get_a_tab()


def test_set_ua():
    # check the UA changed
    tab.set_ua('No UA.')
    tab.set_url('http://httpbin.org/user-agent')
    assert 'No UA.' in tab.html, tab.html


def test_mouse_keyboard():
    # click the input element and send some string
    tab.set_url('http://httpbin.org/forms/post', timeout=5)
    rect: dict = tab.get_bounding_client_rect('[type="email"]')
    tab.mouse_click(rect['left'], rect['top'], count=1)
    tab.keyboard_send(string='123@1.com')
    # click the submit button
    tab.click('button')
    tab.wait_loading(2)
    assert '"custemail": "123@1.com"' in tab.html, tab.html


def test_js():
    tab.set_url('https://postman-echo.com/ip')
    tag = tab.querySelectorAll('html')[0]
    print(tag, tag.text)
    img_b64 = tab.screenshot_element('html')
    tab.set_html(
        f'<h1>Here is the screenshot image by css selector ".shader_left"</h1><img src="data:image/png;base64, {img_b64}" alt="Red dot" /><h1>Test js finished</h1>'
    )


def main():
    test_set_ua()
    test_mouse_keyboard()
    test_js()
    for _ in range(3):
        tab.set_html(
            f'<h1>Start network_sniffer in %s seconds. Refresh this page and read network logs in terminal.</h1>'
            % (3 - _))
        time.sleep(1)
    network_sniffer()


if __name__ == "__main__":
    try:
        main()
    finally:
        daemon.stop_running()
