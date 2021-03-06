import time

from ichrome import AsyncTab
from ichrome.debugger import get_a_tab, network_sniffer

# There are 3 ways to create a daemon
# 1. get_a_tab: auto find the existing Chrome (launched before like python -m ichrome), or create a new daemon
# 2. daemon = Daemon()
# 3. daemon = launch()

# type hints for autocomplete in the IDE
tab: AsyncTab = get_a_tab()


def test_set_ua():
    # check the UA changed
    tab.set_ua('No UA.')
    tab.set_url('http://httpbin.org/user-agent')
    assert 'No UA.' in tab.html


def test_mouse_keyboard():
    # click the input element and send some string
    tab.set_url('http://httpbin.org/forms/post', timeout=3)
    rect: dict = tab.get_bounding_client_rect('[type="email"]')
    tab.mouse_click(rect['left'], rect['top'], count=1)
    tab.keyboard_send(string='123@1.com')
    # click the submit button
    tab.click('button')
    tab.wait_loading(2)
    assert '"custemail": "123@1.com"' in tab.html


def test_js():
    tab.set_url('http://bing.com')
    tag = tab.querySelectorAll('.shader_left')[0]
    print(tag, tag.text)
    img_b64 = tab.screenshot_element('.shader_left')
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
    # explicitly stop daemon is not necessary, daemon launched by debugger will auto shutdown after this script quit
    # if the daemon is not launched by this script (using an existing one), the auto-shutdown will not run.
    # daemon.stop()


if __name__ == "__main__":
    main()
