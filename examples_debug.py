import time

from ichrome import AsyncTab
from ichrome.debugger import Chrome, Daemon

# There are 3 ways to create a daemon
# 1. get_a_tab: auto find the existing Chrome (launched before like python -m ichrome), or create a new daemon
# 2. daemon = Daemon()
# 3. daemon = launch()


def test_set_ua(tab: AsyncTab):
    # check the UA changed
    tab.set_ua("Custom UA.")
    tab.set_url("http://httpbin.org/user-agent")
    assert "Custom UA." in tab.html, tab.html


def test_mouse_keyboard(tab: AsyncTab):
    # click the input element and send some string
    tab.set_url("http://httpbin.org/forms/post", timeout=5)
    rect: dict = tab.get_bounding_client_rect('[type="email"]')
    tab.mouse_click(rect["left"], rect["top"], count=1)
    tab.keyboard_send(string="123@1.com")
    # click the submit button
    tab.click("button")
    tab.wait_loading(3)
    assert '"custemail": "123@1.com"' in tab.html, tab.html


def test_js(tab: AsyncTab):
    tab.set_url("https://help.tom.com/")
    tag = tab.querySelectorAll(".pr_tit")[0]
    assert tag and tag.text
    from html import escape

    tab.run_js_snippets("add_tip", f"got the .pr_tit tag[0]: {escape(tag.outerHTML)}")
    time.sleep(3)
    tab.run_js_snippets("clear_tip")
    img_b64 = tab.screenshot_element("#contact", captureBeyondViewport=True)
    tab.set_html(
        f'<h1>Here is the screenshot image by css selector "#contact"</h1><img style="width:80%;" src="data:image/png;base64, {img_b64}" alt="Red dot" /><h1>Test js finished after 5 secs</h1>'
    )
    tab.alert('Here is the screenshot image by css selector "#contact"')
    for i in range(5):
        tab.run_js_snippets("add_tip", f"{5 - i}s")
        time.sleep(1)


def main():
    with Daemon(
        user_data_dir="./debug_cache", clear_after_shutdown=True, headless=0
    ) as daemon:
        with Chrome(host=daemon.host, port=daemon.port) as chrome:
            tab = chrome.get_tab()
            test_set_ua(tab)
            test_mouse_keyboard(tab)
            test_js(tab)


if __name__ == "__main__":
    main()
