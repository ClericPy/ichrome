A poor document... Maybe read the source code is a better choice.

Help on class AsyncChromeDaemon in module ichrome.daemon:

class AsyncChromeDaemon(ChromeDaemon)
 |  AsyncChromeDaemon(chrome_path=None, host='127.0.0.1', port=9222, headless=False, user_agent=None, proxy=None, user_data_dir=None, disable_image=False, start_url='', extra_config=None, max_deaths=1, daemon=True, block=False, timeout=3, debug=False, proc_check_interval=5, on_startup=None, on_shutdown=None, before_startup=None, after_shutdown=None, clear_after_shutdown=False, popen_kwargs: dict = None)
 |  
 |  Create chrome process, and auto restart if it crash too fast.
 |  max_deaths: max_deaths=2 means should quick shutdown chrome twice to skip auto_restart. Default 1.
 |  
 |      chrome_path=None,     chrome executable file path, default to null for
 |                            automatic searching
 |      host="127.0.0.1",     --remote-debugging-address, default to 127.0.0.1
 |      port,                 --remote-debugging-port, default to 9222
 |      headless,             --headless and --hide-scrollbars, default to False
 |      user_agent,           --user-agent, default to None (with the original UA)
 |      proxy,                --proxy-server, default to None
 |      user_data_dir,        user_data_dir to save the user data, default to ~/ichrome_user_data. These strings will ignore user_data_dir arg: {'null', 'None', '/dev/null', "''", '""'}
 |      disable_image,        disable image for loading performance, default to False
 |      start_url,            start url while launching chrome, default to None
 |      max_deaths,           max deaths in 5 secs, auto restart `max_deaths` times if crash fast in 5 secs. default to 1 (without auto-restart)
 |      timeout,              timeout to connect the remote server, default to 1 for localhost
 |      debug,                set logger level to DEBUG
 |      proc_check_interval,  check chrome process alive every interval seconds
 |  
 |      on_startup & on_shutdown: function which handled a ChromeDaemon object while startup or shutdown
 |  
 |  default extra_config: ["--disable-gpu", "--no-first-run"], root user may need append "--no-sandbox"
 |  https://github.com/GoogleChrome/chrome-launcher/blob/master/docs/chrome-flags-for-tools.md
 |  
 |  common args:
 |  
 |      --incognito: Causes the browser to launch directly in incognito mode
 |      --mute-audio: Mutes audio sent to the audio device so it is not audible during automated testing.
 |      --blink-settings=imagesEnabled=false: disable image loading.
 |      --no-sandbox
 |      --disable-javascript
 |      --disable-extensions
 |      --disable-background-networking
 |      --safebrowsing-disable-auto-update
 |      --disable-sync
 |      --ignore-certificate-errors
 |      –disk-cache-dir=xxx: Use a specific disk cache location, rather than one derived from the UserDatadir.
 |      --disk-cache-size: Forces the maximum disk space to be used by the disk cache, in bytes.
 |      --single-process
 |      --proxy-pac-url=xxx. Nonsense for headless mode.
 |      --kiosk
 |      --window-size=800,600
 |      --disable-logging
 |      --disable-component-extensions-with-background-pages
 |      --disable-default-apps
 |      --disable-login-animations
 |      --disable-notifications
 |      --disable-print-preview
 |      --disable-prompt-on-repost
 |      --disable-setuid-sandbox
 |      --disable-system-font-check
 |      --disable-dev-shm-usage
 |      --aggressive-cache-discard
 |      --aggressive-tab-discard
 |      --mem-pressure-system-reserved-kb=80000
 |      --disable-shared-workers
 |      --disable-gl-drawing-for-tests
 |      --use-gl=swiftshader
 |      --disable-canvas-aa
 |      --disable-2d-canvas-clip-aa
 |      --disable-breakpad
 |      --no-zygote
 |      --disable-reading-from-canvas
 |      --disable-remote-fonts
 |      --renderer-process-limit=1
 |      --disable-hang-monitor
 |      --disable-client-side-phishing-detection
 |      --disable-translate
 |      --password-store=basic
 |      --disable-popup-blocking
 |      --no-service-autorun
 |      --no-default-browser-check
 |      --autoplay-policy=user-gesture-required
 |      --disable-device-discovery-notifications
 |      --disable-component-update
 |      --disable-domain-reliability
 |      --enable-automation
 |  
 |  
 |  see more args: https://peter.sh/experiments/chromium-command-line-switches/
 |  
 |  
 |  demo::
 |  
 |      import asyncio
 |      import json
 |  
 |      from ichrome import AsyncChromeDaemon
 |  
 |  
 |      async def main():
 |          async with AsyncChromeDaemon(clear_after_shutdown=True,
 |                                      headless=False,
 |                                      disable_image=False,
 |                                      user_data_dir='./ichrome_user_data') as cd:
 |              async with cd.connect_tab(0, auto_close=True) as tab:
 |                  loaded = await tab.goto('https://httpbin.org/forms/post',
 |                                          timeout=10)
 |                  html = await tab.html
 |                  title = await tab.title
 |                  print(
 |                      f'page loaded ok: {loaded}, HTML length is {len(html)}, title is "{title}"'
 |                  )
 |                  # try setting the input tag value with JS
 |                  await tab.js(
 |                      r"""document.querySelector('[value="bacon"]').checked = true""")
 |                  # or you can click the checkbox
 |                  await tab.click('[value="cheese"]')
 |                  # you can set the value of input
 |                  await tab.js(
 |                      r"""document.querySelector('[name="custname"]').value = "1234" """
 |                  )
 |                  # now click the submit button
 |                  await tab.click('form button')
 |                  await tab.wait_loading(5)
 |                  # extract the JSON with regex
 |                  result = await tab.findone(r'<pre.*?>([\s\S]*?)</pre>')
 |                  print(json.loads(result))
 |  
 |  
 |      if __name__ == "__main__":
 |          asyncio.run(main())
 |  
 |  Method resolution order:
 |      AsyncChromeDaemon
 |      ChromeDaemon
 |      builtins.object
 |  
 |  Methods defined here:
 |  
 |  async __aenter__(self)
 |  
 |  async __aexit__(self, *args, **kwargs)
 |  
 |  __del__(self)
 |  
 |  __init__(self, chrome_path=None, host='127.0.0.1', port=9222, headless=False, user_agent=None, proxy=None, user_data_dir=None, disable_image=False, start_url='', extra_config=None, max_deaths=1, daemon=True, block=False, timeout=3, debug=False, proc_check_interval=5, on_startup=None, on_shutdown=None, before_startup=None, after_shutdown=None, clear_after_shutdown=False, popen_kwargs: dict = None)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  async check_chrome_ready(self)
 |      check if the chrome api is available
 |  
 |  async check_connection(self)
 |      check chrome connection ok
 |  
 |  async clear_user_data_dir(self)
 |  
 |  async close_browser(self)
 |      close browser peacefully
 |  
 |  connect_tab(self, index: Union[NoneType, int, str] = 0, auto_close: bool = False, flatten: bool = None)
 |      More easier way to init a connected Tab with `async with`.
 |      
 |      Got a connected Tab object by using `async with chromed.connect_tab(0) as tab:`
 |      
 |          index = 0 means the current tab.
 |          index = None means create a new tab.
 |          index = 'http://python.org' means create a new tab with url.
 |          index = 'F130D0295DB5879791AA490322133AFC' means the tab with this id.
 |      
 |          If auto_close is True: close this tab while exiting context.
 |      
 |          View more about flatten: https://chromedevtools.github.io/devtools-protocol/tot/Target/#method-attachToTarget
 |  
 |  create_context(self, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None) -> ichrome.async_utils.BrowserContext
 |      create a new browser context, which can be set new proxy, same like the incognito mode
 |  
 |  async get_local_state(self)
 |      Get the dict from {self.user-data-dir}/Local State which including online user profiles info.
 |      WARNING: return None while self.user_data_dir is not set, and new folder may not have this file until chrome process run more than 10 secs.
 |  
 |  incognito_tab(self, url: str = 'about:blank', width: int = None, height: int = None, enableBeginFrameControl: bool = None, newWindow: bool = None, background: bool = None, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None, flatten: bool = None)
 |      create a new tab with incognito mode, this is really a good choice
 |  
 |  init(self)
 |  
 |  async launch_chrome(self)
 |      launch the chrome with remote-debugging mode
 |  
 |  async restart(self)
 |      restart the chrome process
 |  
 |  async run_forever(self, block=True, interval=None)
 |      start the daemon and ensure proc is alive
 |  
 |  async shutdown(self, reason=None)
 |      shutdown the chrome, but do not use it, use async with instead.
 |  
 |  ----------------------------------------------------------------------
 |  Class methods defined here:
 |  
 |  async get_free_port(host='127.0.0.1', start=9222, max_tries=100, timeout=1) from builtins.type
 |      find a free port which can be used
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties defined here:
 |  
 |  connection_ok
 |  
 |  loop
 |  
 |  ok
 |  
 |  req
 |  
 |  x
 |  
 |  ----------------------------------------------------------------------
 |  Methods inherited from ChromeDaemon:
 |  
 |  __enter__(self)
 |  
 |  __exit__(self, *args)
 |  
 |  __repr__(self)
 |      Return repr(self).
 |  
 |  __str__(self)
 |      Return str(self).
 |  
 |  get_cmd_args(self)
 |  
 |  get_memory(self, attr='uss', unit='MB')
 |      Only support local Daemon. `uss` is slower than `rss` but useful.
 |  
 |  kill(self, force=False)
 |  
 |  update_shutdown_time(self)
 |  
 |  ----------------------------------------------------------------------
 |  Class methods inherited from ChromeDaemon:
 |  
 |  clear_dir(dir_path) from builtins.type
 |  
 |  clear_user_dir(user_data_dir=None, port=None) from builtins.type
 |      WARNING: this is a sync class method, if you want to clear only user dir, use self.clear_user_data_dir instead
 |  
 |  get_chrome_path() from builtins.type
 |  
 |  ----------------------------------------------------------------------
 |  Static methods inherited from ChromeDaemon:
 |  
 |  clear_chrome_process(port=None, timeout=None, max_deaths=1, interval=0.5, host=None)
 |  
 |  clear_dir_with_shutil(dir_path)
 |  
 |  ensure_dir(path: pathlib.Path)
 |  
 |  get_dir_size(path)
 |  
 |  get_proc(port, host=None)
 |  
 |  get_readable_dir_size(path)
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties inherited from ChromeDaemon:
 |  
 |  cmd
 |  
 |  proc_ok
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors inherited from ChromeDaemon:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)
 |  
 |  ----------------------------------------------------------------------
 |  Data and other attributes inherited from ChromeDaemon:
 |  
 |  DEFAULT_EXTRA_CONFIG = ['--disable-gpu', '--no-first-run']
 |  
 |  DEFAULT_POPEN_ARGS = {'start_new_session': True}
 |  
 |  DEFAULT_USER_DIR_PATH = WindowsPath('C:/Users/ld/ichrome_user_data')
 |  
 |  IGNORE_USER_DIR_FLAGS = {'""', "''", '/dev/null', 'None', 'null'}
 |  
 |  IPAD_UA = 'Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) Ap... Gecko) ...
 |  
 |  MAC_OS_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0_1) Version/8....
 |  
 |  MAX_WAIT_CHECKING_SECONDS = 15
 |  
 |  MOBILE_UA = 'Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/... Gecko...
 |  
 |  PC_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537....L, like Ge...
 |  
 |  WECHAT_UA = 'Mozilla/5.0 (Linux; Android 5.0; SM-N9100 Build/... Micro...

Help on class AsyncTab in module ichrome.async_utils:

class AsyncTab(GetValueMixin)
 |  AsyncTab(tab_id: str = None, title: str = None, url: str = None, type: str = None, description: str = None, webSocketDebuggerUrl: str = None, devtoolsFrontendUrl: str = None, json: str = None, chrome: 'AsyncChrome' = None, timeout=Ellipsis, ws_kwargs: dict = None, default_recv_callback: Callable = None, _recv_daemon_break_callback: Callable = None, flatten: bool = None, **kwargs)
 |  
 |  Tab operations in async environment.
 |  
 |  The timeout variable -- wait for the events::
 |  
 |      NotSet:
 |          using the self.timeout by default
 |      None:
 |          using the self._MAX_WAIT_TIMEOUT instead, default to float('inf')
 |      0:
 |          no wait
 |      int / float:
 |          wait `timeout` seconds
 |  
 |  Method resolution order:
 |      AsyncTab
 |      GetValueMixin
 |      builtins.object
 |  
 |  Methods defined here:
 |  
 |  __call__(self) -> ichrome.async_utils._WSConnection
 |      `async with tab() as tab:` or just `async with tab():` and reuse `tab` variable.
 |  
 |  __eq__(self, other)
 |      Return self==value.
 |  
 |  __hash__(self)
 |      Return hash(self).
 |  
 |  __init__(self, tab_id: str = None, title: str = None, url: str = None, type: str = None, description: str = None, webSocketDebuggerUrl: str = None, devtoolsFrontendUrl: str = None, json: str = None, chrome: 'AsyncChrome' = None, timeout=Ellipsis, ws_kwargs: dict = None, default_recv_callback: Callable = None, _recv_daemon_break_callback: Callable = None, flatten: bool = None, **kwargs)
 |      original Tab JSON::
 |      
 |          [{
 |              "description": "",
 |              "devtoolsFrontendUrl": "/devtools/inspector.html?ws=localhost:9222/devtools/page/8ED4BDD54713572BCE026393A0137214",
 |              "id": "8ED4BDD54713572BCE026393A0137214",
 |              "title": "about:blank",
 |              "type": "page",
 |              "url": "http://localhost:9222/json",
 |              "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/8ED4BDD54713572BCE026393A0137214"
 |          }]
 |      :param tab_id: defaults to kwargs.pop('id')
 |      :type tab_id: str, optional
 |      :param title: tab title, defaults to None
 |      :type title: str, optional
 |      :param url: tab url, binded to self._url, defaults to None
 |      :type url: str, optional
 |      :param type: tab type, often be `page` type, defaults to None
 |      :type type: str, optional
 |      :param description: tab description, defaults to None
 |      :type description: str, optional
 |      :param webSocketDebuggerUrl: ws URL to connect, defaults to None
 |      :type webSocketDebuggerUrl: str, optional
 |      :param devtoolsFrontendUrl: devtools UI URL, defaults to None
 |      :type devtoolsFrontendUrl: str, optional
 |      :param json: raw Tab JSON, defaults to None
 |      :type json: str, optional
 |      :param chrome: the Chrome object which the Tab belongs to, defaults to None
 |      :type chrome: Chrome, optional
 |      :param timeout: default recv timeout, defaults to Tab._DEFAULT_RECV_TIMEOUT
 |      :type timeout: [type], optional
 |      :param ws_kwargs: kwargs for ws connection, defaults to None
 |      :type ws_kwargs: dict, optional
 |      :param default_recv_callback: called for each data received, sync/async function only accept 1 arg of data comes from ws recv, defaults to None
 |      :type default_recv_callback: Callable, optional
 |      :param _recv_daemon_break_callback: like the tab_close_callback. sync/async function only accept 1 arg of self while _recv_daemon break, defaults to None
 |      :type _recv_daemon_break_callback: Callable, optional
 |      :param flatten: use flatten mode with sessionId
 |      :type flatten: bool, optional
 |  
 |  __repr__(self)
 |      Return repr(self).
 |  
 |  __str__(self)
 |      Return str(self).
 |  
 |  async activate(self, timeout=Ellipsis) -> Optional[dict]
 |      [Page.bringToFront], activate tab with cdp websocket
 |  
 |  async activate_tab(self) -> Union[str, bool]
 |      activate tab with chrome http endpoint
 |  
 |  async add_js_onload(self, source: str, **kwargs) -> str
 |      [Page.addScriptToEvaluateOnNewDocument], return the identifier [str].
 |  
 |  async alert(self, text, timeout=Ellipsis)
 |      run alert(`{text}`) in console, the `text` should be escaped before passing.
 |      Block until user click [OK] or timeout.
 |      Returned as:
 |          "undefined": [OK] clicked.
 |          None: timeout.
 |  
 |  async auto_enable(self, event_or_method, timeout=Ellipsis)
 |      auto enable the domain
 |  
 |  async clear_browser_cache(self, timeout=Ellipsis)
 |      [Network.clearBrowserCache]
 |  
 |  async clear_browser_cookies(self, timeout=Ellipsis)
 |      [Network.clearBrowserCookies]
 |  
 |  async click(self, cssselector: str, index: int = 0, action: str = 'click()', timeout=Ellipsis) -> Union[List[ichrome.base.Tag], ichrome.base.Tag, NoneType]
 |      Click some tag with javascript
 |      await tab.click("#sc_hdu>li>a") # click first node's link.
 |      await tab.click("#sc_hdu>li>a", index=3, action="removeAttribute('href')") # remove href of the a tag.
 |  
 |  async close(self, timeout=0) -> Optional[dict]
 |      [Page.close], close tab with cdp websocket. will lose ws, so timeout default to 0.
 |  
 |  async close_browser(self, timeout=0)
 |  
 |  async close_tab(self) -> Union[str, bool]
 |      close tab with chrome http endpoint
 |  
 |  async confirm(self, text, timeout=Ellipsis)
 |      run confirm(`{text}`) in console, the `text` should be escaped before passing.
 |      Block until user click [OK] or click [Cancel] or timeout.
 |      Returned as:
 |          True: [OK] clicked.
 |          False: [Cancel] clicked.
 |          None: timeout.
 |  
 |  connect(self) -> ichrome.async_utils._WSConnection
 |      `async with tab.connect() as tab:`
 |  
 |  async contains(self, text, cssselector: str = 'html', attribute: str = 'outerHTML', timeout=Ellipsis) -> bool
 |      alias for Tab.includes
 |  
 |  async crash(self, timeout=0) -> Optional[dict]
 |      [Page.crash], will lose ws, so timeout default to 0.
 |  
 |  async delete_cookies(self, name: str, url: Optional[str] = '', domain: Optional[str] = '', path: Optional[str] = '', timeout=Ellipsis)
 |      [Network.deleteCookies], deleteCookies by name, with url / domain / path.
 |  
 |  async disable(self, domain: str, force: bool = False, timeout=Ellipsis)
 |      domain: Network / Page and so on, will send `domain.disable`. Automatically check for duplicated sendings if not force.
 |  
 |  async enable(self, domain: str, force: bool = False, timeout=None, kwargs: dict = None, **_kwargs)
 |      domain: Network or Page and so on, will send `{domain}.enable`. Automatically check for duplicated sendings if not force.
 |  
 |  ensure_timeout(self, timeout)
 |      replace the timeout variable to real value
 |  
 |  async findall(self, regex: str, cssselector: str = 'html', attribute: str = 'outerHTML', flags: str = 'g', timeout=Ellipsis) -> list
 |      Similar to python re.findall.
 |      
 |      Demo::
 |      
 |          # no group / (?:) / (?<=) / (?!)
 |          print(await tab.findall('<title>.*?</title>'))
 |          # ['<title>123456789</title>']
 |      
 |          # only 1 group
 |          print(await tab.findall('<title>(.*?)</title>'))
 |          # ['123456789']
 |      
 |          # multi-groups
 |          print(await tab.findall('<title>(1)(2).*?</title>'))
 |          # [['1', '2']]
 |      
 |      :param regex: raw regex string to be set in /%s/g
 |      :type regex: str
 |      :param cssselector: which element.outerHTML to be matched, defaults to 'html'
 |      :type cssselector: str, optional
 |      :param attribute: attribute of the selected element, defaults to 'outerHTML'
 |      :type attribute: str, optional
 |      :param flags: regex flags, defaults to 'g'
 |      :type flags: str, optional
 |      :param timeout: defaults to NotSet
 |      :type timeout: [type], optional
 |  
 |  async findone(self, regex: str, cssselector: str = 'html', attribute: str = 'outerHTML', timeout=Ellipsis)
 |      find the string in html(select with given css)
 |  
 |  async gc(self)
 |      [HeapProfiler.collectGarbage]
 |  
 |  async get_all_cookies(self, timeout=Ellipsis)
 |      [Network.getAllCookies], return all the cookies of this browser.
 |  
 |  async get_cookies(self, urls: Union[List[str], str] = None, timeout=Ellipsis) -> List
 |      [Network.getCookies], get cookies of urls.
 |  
 |  async get_current_title(self, timeout=Ellipsis) -> str
 |      JS: document.title
 |  
 |  async get_current_url(self, timeout=Ellipsis) -> str
 |      JS: window.location.href
 |  
 |  async get_element_clip(self, cssselector: str, scale=1, timeout=Ellipsis, captureBeyondViewport=False)
 |      Element.getBoundingClientRect. If captureBeyondViewport is True, use scrollWidth & scrollHeight instead.
 |      {"x":241,"y":85.59375,"width":165,"height":36,"top":85.59375,"right":406,"bottom":121.59375,"left":241}
 |  
 |  async get_frame_tree(self, timeout=Ellipsis)
 |      [Page.getFrameTree], get current page frame tree
 |  
 |  async get_history_entry(self, index: int = None, relative_index: int = None, timeout=Ellipsis)
 |      get history entries of this page
 |  
 |  async get_history_list(self, timeout=Ellipsis) -> dict
 |      return dict: {'currentIndex': 0, 'entries': [{'id': 1, 'url': 'about:blank', 'userTypedURL': 'about:blank', 'title': '', 'transitionType': 'auto_toplevel'}, {'id': 7, 'url': 'http://3.p.cn/', 'userTypedURL': 'http://3.p.cn/', 'title': 'Not Found', 'transitionType': 'typed'}, {'id': 9, 'url': 'http://p.3.cn/', 'userTypedURL': 'http://p.3.cn/', 'title': '', 'transitionType': 'typed'}]}}
 |  
 |  async get_html(self, timeout=Ellipsis) -> str
 |      return html from `document.documentElement.outerHTML`
 |  
 |  async get_page_frame_id(self, timeout=Ellipsis)
 |      get frame id of current page
 |  
 |  async get_page_size(self, timeout=Ellipsis)
 |      get page size with javascript
 |  
 |  async get_request_post_data(self, request_dict: Union[NoneType, dict, str], timeout=Ellipsis) -> Optional[str]
 |      Get the post data of the POST request. No need for wait_request_loading.
 |  
 |  async get_response(self, request_dict: Union[NoneType, dict, str], timeout=Ellipsis, wait_loading: bool = None) -> Optional[dict]
 |      return Network.getResponseBody raw response.
 |      return demo:
 |      
 |              {'id': 2, 'result': {'body': 'source code', 'base64Encoded': False}}
 |      
 |      some ajax request need to await tab.wait_request_loading(request_dict) for
 |      loadingFinished (or sleep some secs) and wait_loading=None will auto check response loaded.
 |  
 |  async get_response_body(self, request_dict: Union[NoneType, dict, str], timeout=Ellipsis, wait_loading=None) -> Optional[dict]
 |      get result.body from self.get_response.
 |  
 |  async get_screen_size(self, timeout=Ellipsis)
 |      get [window.screen.width, window.screen.height] with javascript
 |  
 |  async get_value(self, name: str, timeout=Ellipsis, jsonify: bool = False)
 |      name or expression. jsonify will transport the data by JSON, such as the array.
 |  
 |  async get_variable(self, name: str, timeout=Ellipsis, jsonify: bool = False)
 |      variable or expression. jsonify will transport the data by JSON, such as the array.
 |  
 |  async goto(self, url: Optional[str] = None, referrer: Optional[str] = None, timeout=Ellipsis, timeout_stop_loading: bool = False) -> bool
 |      alias for self.set_url
 |  
 |  async goto_history(self, entryId: int = 0, timeout=Ellipsis) -> bool
 |      [Page.navigateToHistoryEntry]
 |  
 |  async goto_history_relative(self, relative_index: int = None, timeout=Ellipsis)
 |      go to the relative history
 |  
 |  async handle_dialog(self, accept=True, promptText=None, timeout=Ellipsis) -> bool
 |      WARNING: you should enable `Page` domain explicitly before running tab.js('alert()'), because alert() will always halt the event loop.
 |  
 |  async history_back(self, timeout=Ellipsis)
 |      go to back history
 |  
 |  async history_forward(self, timeout=Ellipsis)
 |      go to forward history
 |  
 |  async includes(self, text, cssselector: str = 'html', attribute: str = 'outerHTML', timeout=Ellipsis) -> bool
 |      String.prototype.includes.
 |      
 |      :param text: substring
 |      :type text: str
 |      :param cssselector: css selector for outerHTML, defaults to 'html'
 |      :type cssselector: str, optional
 |      :param attribute: attribute of the selected element, defaults to 'outerHTML'. Sometimes for case-insensitive usage by setting `attribute='textContent.toLowerCase()'`
 |      :type attribute: str, optional
 |      :return: whether the outerHTML contains substring.
 |      :rtype: bool
 |  
 |  async inject_html(self, html: str, cssselector: str = 'body', position: str = 'beforeend', timeout=Ellipsis)
 |      An alias name for tab.insertAdjacentHTML.
 |  
 |  async inject_js_url(self, url, timeout=None, retry=0, verify=False, **requests_kwargs) -> Optional[dict]
 |      inject and run the given JS URL
 |  
 |  async insertAdjacentHTML(self, html: str, cssselector: str = 'body', position: str = 'beforeend', timeout=Ellipsis)
 |      Insert HTML source code into document. Often used for injecting CSS element.
 |      
 |      :param html: HTML source code
 |      :type html: str
 |      :param cssselector: cssselector to find the target node, defaults to 'body'
 |      :type cssselector: str, optional
 |      :param position: ['beforebegin', 'afterbegin', 'beforeend', 'afterend'],  defaults to 'beforeend'
 |      :type position: str, optional
 |      :param timeout: defaults to NotSet
 |      :type timeout: [type], optional
 |      :return: [description]
 |      :rtype: [type]
 |  
 |  iter_events(self, events: List[str], timeout: Union[float, int] = None, maxsize=0, kwargs: Any = None, callback: Callable = None) -> 'EventBuffer'
 |      Iter events with a async context.
 |      ::
 |      
 |          async with AsyncChromeDaemon() as cd:
 |              async with cd.connect_tab() as tab:
 |                  async with tab.iter_events(['Page.loadEventFired'],
 |                                          timeout=60) as e:
 |                      await tab.goto('http://httpbin.org/get')
 |                      print(await e)
 |                      # {'method': 'Page.loadEventFired', 'params': {'timestamp': 1380679.967344}}
 |                      # await tab.goto('http://httpbin.org/get')
 |                      # print(await e.get())
 |                      # # {'method': 'Page.loadEventFired', 'params': {'timestamp': 1380679.967344}}
 |                      await tab.goto('http://httpbin.org/get')
 |                      async for data in e:
 |                          print(data)
 |                          break
 |  
 |  iter_fetch(self, patterns: List[dict] = None, handleAuthRequests=False, events: List[str] = None, timeout: Union[float, int] = None, maxsize=0, kwargs: Any = None, callback: Callable = None) -> 'FetchBuffer'
 |      Fetch.RequestPattern:
 |          urlPattern
 |              string(Wildcards)
 |          resourceType
 |              Document, Stylesheet, Image, Media, Font, Script, TextTrack, XHR, Fetch, EventSource, WebSocket, Manifest, SignedExchange, Ping, CSPViolationReport, Preflight, Other
 |          requestStage
 |              Stage at which to begin intercepting requests. Default is Request.
 |              Allowed Values: Request, Response
 |              ::
 |      
 |                  async with tab.iter_fetch(patterns=[{
 |                          'urlPattern': '*httpbin.org/get?a=*'
 |                  }]) as f:
 |                      await tab.goto('http://httpbin.org/get?a=1', timeout=0)
 |                      data = await f
 |                      assert data
 |                      # test continueRequest
 |                      await f.continueRequest(data)
 |                      assert await tab.wait_includes('origin')
 |      
 |                      await tab.goto('http://httpbin.org/get?a=1', timeout=0)
 |                      data = await f
 |                      assert data
 |                      # test modify response
 |                      await f.fulfillRequest(data,
 |                                             200,
 |                                             body=b'hello world.')
 |                      assert await tab.wait_includes('hello world.')
 |                      await tab.goto('http://httpbin.org/get?a=1', timeout=0)
 |                      data = await f
 |                      assert data
 |                      await f.failRequest(data, 'AccessDenied')
 |                      assert (await tab.url).startswith('chrome-error://')
 |      
 |                  # use callback
 |                  async def cb(event, tab, buffer):
 |                      await buffer.continueRequest(event)
 |      
 |                  async with tab.iter_fetch(
 |                          patterns=[{
 |                              'urlPattern': '*httpbin.org/ip*'
 |                          }],
 |                          callback=cb,
 |                  ) as f:
 |                      await tab.goto('http://httpbin.org/ip', timeout=0)
 |                      async for r in f:
 |                          break
 |  
 |  async js(self, javascript: str, value_path='result.result', kwargs=None, timeout=Ellipsis)
 |      Evaluate JavaScript on the page.
 |      `js_result = await tab.js('document.title', timeout=10)`
 |      js_result:
 |          {'id': 18, 'result': {'result': {'type': 'string', 'value': 'Welcome to Python.org'}}}
 |      return None while timeout.
 |      kwargs is a dict for Runtime.evaluate's `timeout` is conflict with `timeout` of self.send.
 |  
 |  async js_code(self, javascript: str, value_path='result.result.value', kwargs=None, timeout=Ellipsis)
 |      javascript will be filled into function template.
 |      Demo::
 |          javascript = `return document.title`
 |          will run js like, and get the return result
 |          `(()=>{return document.title})()`
 |  
 |  async keyboard_send(self, *, type='char', timeout=Ellipsis, string=None, **kwargs)
 |      [Input.dispatchKeyEvent]
 |      
 |      type: keyDown, keyUp, rawKeyDown, char.
 |      string: will be split into chars.
 |      
 |      kwargs:
 |          text, unmodifiedText, keyIdentifier, code, key...
 |      
 |      https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchKeyEvent
 |  
 |  async mouse_click(self, x, y, button='left', count=1, timeout=Ellipsis)
 |      click a position
 |  
 |  async mouse_click_element_rect(self, cssselector: str, button='left', count=1, scale=1, multiplier=(0.5, 0.5), timeout=Ellipsis)
 |      dispatchMouseEvent on selected element center
 |  
 |  async mouse_drag(self, start_x, start_y, target_x, target_y, button='left', duration=0, timeout=Ellipsis)
 |  
 |  async mouse_drag_rel(self, start_x, start_y, offset_x, offset_y, button='left', duration=0, timeout=Ellipsis)
 |      drag mouse relatively
 |  
 |  mouse_drag_rel_chain(self, start_x, start_y, button='left', timeout=Ellipsis)
 |      Drag with offset continuously.
 |      
 |      Demo::
 |      
 |              await tab.set_url('https://draw.yunser.com/')
 |              walker = await tab.mouse_drag_rel_chain(320, 145).move(50, 0, 0.2).move(
 |                  0, 50, 0.2).move(-50, 0, 0.2).move(0, -50, 0.2)
 |              await walker.move(50 * 1.414, 50 * 1.414, 0.2)
 |  
 |  async mouse_move(self, target_x, target_y, start_x=None, start_y=None, duration=0, timeout=Ellipsis)
 |      move mouse smoothly only if duration > 0.
 |  
 |  async mouse_move_rel(self, offset_x, offset_y, start_x, start_y, duration=0, timeout=Ellipsis)
 |      Move mouse with offset.
 |      
 |      Example::
 |      
 |              await tab.mouse_move_rel(x + 15, 3, start_x, start_y, duration=0.3)
 |  
 |  mouse_move_rel_chain(self, start_x, start_y, timeout=Ellipsis)
 |      Move with offset continuously.
 |      
 |      Example::
 |      
 |          walker = await tab.mouse_move_rel_chain(start_x, start_y).move(-20, -5, 0.2).move(5, 1, 0.2)
 |          walker = await walker.move(-10, 0, 0.2).move(10, 0, 0.5)
 |  
 |  async mouse_press(self, x, y, button='left', count=0, timeout=Ellipsis)
 |      Input.dispatchMouseEvent + mousePressed
 |  
 |  async mouse_release(self, x, y, button='left', count=0, timeout=Ellipsis)
 |      Input.dispatchMouseEvent + mouseReleased
 |  
 |  async prompt(self, text, value=None, timeout=Ellipsis)
 |      run prompt(`{text}`, `value`) in console, the `text` and `value` should be escaped before passing.
 |      Block until user click [OK] or click [Cancel] or timeout.
 |      Returned as:
 |          new value: [OK] clicked.
 |          None: [Cancel] clicked.
 |          value: timeout.
 |  
 |  async querySelector(self, cssselector: str, action: Optional[str] = None, timeout=Ellipsis) -> Union[ichrome.base.Tag, ichrome.base.TagNotFound]
 |      query a tag with css
 |  
 |  async querySelectorAll(self, cssselector: str, index: Union[NoneType, int, str] = None, action: Optional[str] = None, timeout=Ellipsis) -> Union[List[ichrome.base.Tag], ichrome.base.Tag, ichrome.base.TagNotFound]
 |      CDP DOM domain is quite heavy both computationally and memory wise, use js instead. return List[Tag], Tag, TagNotFound.
 |      Tag hasattr: tagName, innerHTML, outerHTML, textContent, attributes, result
 |      
 |      If index is not None, will return the tag_list[index], else return the whole tag list.
 |      
 |      Demo:
 |      
 |          # 1. get attribute of the selected tag
 |      
 |          tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0, action="getAttribute('href')")).result
 |          tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0)).get('href')
 |          tags = (await tab.querySelectorAll("#sc_hdu>li>a", index=0)).to_dict()
 |      
 |          # 2. remove href attr of all the selected tags
 |          tags = await tab.querySelectorAll("#sc_hdu>li>a", action="removeAttribute('href')")
 |      
 |          for tag in tab.querySelectorAll("#sc_hdu>li"):
 |              print(tag.attributes)
 |  
 |  recv(self, event_dict: dict, timeout=Ellipsis, callback_function=None) -> Awaitable[Optional[dict]]
 |      Wait for a event_dict or not wait by setting timeout=0. Events will be filt by `id` or `method` or the whole json.
 |      
 |      :param event_dict: dict like {'id': 1} or {'method': 'Page.loadEventFired'} or other JSON serializable dict.
 |      :type event_dict: dict
 |      :param timeout: await seconds, None for self._MAX_WAIT_TIMEOUT, 0 for 0 seconds.
 |      :type timeout: float / None, optional
 |      :param callback_function: event callback_function function accept only one arg(the event dict).
 |      :type callback_function: callable, optional
 |      :return: the event dict from websocket recv.
 |      :rtype: dict
 |  
 |  async refresh_tab_info(self) -> bool
 |      refresh the tab meta info with tab_id from /json
 |  
 |  async reload(self, ignoreCache: bool = False, scriptToEvaluateOnLoad: str = None, timeout=Ellipsis)
 |      Reload the page.
 |      
 |      ignoreCache: If true, browser cache is ignored (as if the user pressed Shift+refresh).
 |      scriptToEvaluateOnLoad: If set, the script will be injected into all frames of the inspected page after reload.
 |      
 |      Argument will be ignored if reloading dataURL origin.
 |  
 |  async remove_js_onload(self, identifier: str, timeout=Ellipsis) -> bool
 |      [Page.removeScriptToEvaluateOnNewDocument], return whether the identifier exist.
 |  
 |  async reset_history(self, timeout=Ellipsis) -> bool
 |      [Page.resetNavigationHistory], clear up history immediately
 |  
 |  async screenshot(self, format: str = 'png', quality: int = 100, clip: dict = None, fromSurface: bool = True, save_path=None, timeout=Ellipsis, captureBeyondViewport=False, **kwargs)
 |      Page.captureScreenshot.
 |      
 |      :param format: Image compression format (defaults to png)., defaults to 'png'
 |      :type format: str, optional
 |      :param quality: Compression quality from range [0..100], defaults to None. (jpeg only).
 |      :type quality: int, optional
 |      :param clip: Capture the screenshot of a given region only. defaults to None, means whole page.
 |      :type clip: dict, optional
 |      :param fromSurface: Capture the screenshot from the surface, rather than the view. Defaults to true.
 |      :type fromSurface: bool, optional
 |      
 |      clip's keys: x, y, width, height, scale
 |  
 |  async screenshot_element(self, cssselector: str = None, scale=1, format: str = 'png', quality: int = 100, fromSurface: bool = True, save_path=None, timeout=Ellipsis, captureBeyondViewport=False, **kwargs)
 |      screenshot the tag selected with given css as a picture
 |  
 |  async send(self, method: str, timeout=Ellipsis, callback_function: Optional[Callable] = None, kwargs: Dict[str, Any] = None, auto_enable=True, force=None, **_kwargs) -> Optional[dict]
 |      Send message to Tab. callback_function only work whlie timeout!=0.
 |      If timeout is not None: wait for recv event.
 |      If auto_enable: will check the domain enabled automatically.
 |      If callback_function: run while received the response msg.
 |      
 |      the `force` arg is deprecated, use auto_enable instead.
 |  
 |  async setBlockedURLs(self, urls: List[str], timeout=Ellipsis)
 |      (Network.setBlockedURLs) Blocks URLs from loading. [EXPERIMENTAL].
 |      :param urls: URL patterns to block. Wildcards ('*') are allowed.
 |      :type urls: List[str]
 |      
 |      Demo::
 |      
 |          await tab.setBlockedURLs(urls=['*.jpg', '*.png'])
 |      
 |      WARNING: This method is EXPERIMENTAL, the official suggestion is using Fetch.enable, even Fetch is also EXPERIMENTAL, and wait events to control the requests (continue / abort / modify), especially block urls with resourceType: Document, Stylesheet, Image, Media, Font, Script, TextTrack, XHR, Fetch, EventSource, WebSocket, Manifest, SignedExchange, Ping, CSPViolationReport, Other.
 |      https://chromedevtools.github.io/devtools-protocol/tot/Fetch/#method-enable
 |  
 |  async set_cookie(self, name: str, value: str, url: Optional[str] = '', domain: Optional[str] = '', path: Optional[str] = '', secure: Optional[bool] = False, httpOnly: Optional[bool] = False, sameSite: Optional[str] = '', expires: Optional[int] = None, timeout=Ellipsis, **_)
 |      [Network.setCookie]
 |      name [string] Cookie name.
 |      value [string] Cookie value.
 |      url [string] The request-URI to associate with the setting of the cookie. This value can affect the default domain and path values of the created cookie.
 |      domain [string] Cookie domain.
 |      path [string] Cookie path.
 |      secure [boolean] True if cookie is secure.
 |      httpOnly [boolean] True if cookie is http-only.
 |      sameSite [CookieSameSite] Cookie SameSite type.
 |      expires [TimeSinceEpoch] Cookie expiration date, session cookie if not set
 |  
 |  async set_cookies(self, cookies: List, ensure_keys=False, timeout=Ellipsis)
 |      [Network.setCookies]
 |  
 |  async set_file_input(self, filepaths: List[Union[str, pathlib.Path]], cssselector: str = 'input[type="file"]', root_id: str = None, timeout=Ellipsis)
 |      set file type input nodes with given filepaths.
 |      1. path of filepaths will be reset as absolute posix path.
 |      2. all the nodes which matched given cssselector will be set together for using DOM.querySelectorAll.
 |      3. nodes in iframe tags need a new root_id but not default gotten from DOM.getDocument.
 |  
 |  set_flatten(self)
 |      use the flatten mode connection
 |  
 |  async set_headers(self, headers: dict, timeout=Ellipsis)
 |      # if 'Referer' in headers or 'referer' in headers:
 |      #     logger.warning('`Referer` is not valid header, please use the `referrer` arg of set_url')
 |  
 |  async set_html(self, html: str, frame_id: str = None, timeout=Ellipsis)
 |      JS: document.write, or Page.setDocumentContent if given frame_id
 |  
 |  async set_ua(self, userAgent: str, acceptLanguage: Optional[str] = '', platform: Optional[str] = '', timeout=Ellipsis)
 |      [Network.setUserAgentOverride], reset the User-Agent of this tab
 |  
 |  async set_url(self, url: Optional[str] = None, referrer: Optional[str] = None, timeout=Ellipsis, timeout_stop_loading: bool = False) -> bool
 |      Navigate the tab to the URL. If stop loading occurs, return False.
 |  
 |  async snapshot_mhtml(self, save_path=None, encoding='utf-8', timeout=Ellipsis, **kwargs)
 |      [Page.captureSnapshot], as the mhtml page
 |  
 |  async stop_loading_page(self, timeout=0)
 |      [Page.stopLoading]
 |  
 |  async wait_console(self, timeout=None, callback_function: Optional[Callable] = None, filter_function: Optional[Callable] = None) -> Optional[dict]
 |      Wait the filted Runtime.consoleAPICalled event.
 |      
 |      consoleAPICalled event types:
 |      log, debug, info, error, warning, dir, dirxml, table, trace, clear, startGroup, startGroupCollapsed, endGroup, assert, profile, profileEnd, count, timeEnd
 |      
 |      return dict or None like:
 |      {'method':'Runtime.consoleAPICalled','params': {'type':'log','args': [{'type':'string','value':'123'}],'executionContextId':13,'timestamp':1592895800590.75,'stackTrace': {'callFrames': [{'functionName':'','scriptId':'344','url':'','lineNumber':0,'columnNumber':8}]}}}
 |  
 |  async wait_console_value(self, timeout=None, callback_function: Optional[Callable] = None, filter_function: Optional[Callable] = None)
 |      Wait the Runtime.consoleAPICalled event, simple data type (null, number, Boolean, string) will try to get value and return.
 |      
 |      This may be very useful for send message from Chrome to Python programs with a JSON string.
 |      
 |      {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'boolean', 'value': True}], 'executionContextId': 4, 'timestamp': 1592924155017.107, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '343', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
 |      {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'object', 'subtype': 'null', 'value': None}], 'executionContextId': 4, 'timestamp': 1592924167384.516, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '362', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
 |      {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'number', 'value': 1, 'description': '1234'}], 'executionContextId': 4, 'timestamp': 1592924176778.166, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '385', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
 |      {'method': 'Runtime.consoleAPICalled', 'params': {'type': 'log', 'args': [{'type': 'string', 'value': 'string'}], 'executionContextId': 4, 'timestamp': 1592924187756.2349, 'stackTrace': {'callFrames': [{'functionName': '', 'scriptId': '404', 'url': '', 'lineNumber': 0, 'columnNumber': 8}]}}}
 |  
 |  async wait_event(self, event_name: str, timeout=None, callback_function: Optional[Callable] = None, filter_function: Optional[Callable] = None) -> Union[dict, NoneType, Any]
 |      Similar to self.recv, but has the filter_function to distinct duplicated method of event.
 |      WARNING: the `timeout` default to None when methods with prefix `wait_`
 |  
 |  async wait_findall(self, regex: str, cssselector: str = 'html', attribute: str = 'outerHTML', flags: str = 'g', max_wait_time: Optional[float] = None, interval: float = 1, timeout=Ellipsis) -> list
 |      while loop until await tab.findall got somethine.
 |  
 |  async wait_includes(self, text: str, cssselector: str = 'html', attribute: str = 'outerHTML', max_wait_time: Optional[float] = None, interval: float = 1, timeout=Ellipsis) -> bool
 |      while loop until element contains the substring.
 |  
 |  async wait_loading(self, timeout=None, callback_function: Optional[Callable] = None, timeout_stop_loading=False) -> bool
 |      wait Page.loadEventFired event while page loaded.
 |      If page loaded event catched, return True.
 |      WARNING: methods with prefix `wait_` the `timeout` default to None.
 |  
 |  async wait_loading_finished(self, request_dict: dict, timeout=None)
 |      wait for the Network.loadingFinished event of given request id
 |  
 |  async wait_page_loading(self, timeout=None, callback_function: Optional[Callable] = None, timeout_stop_loading=False)
 |  
 |  async wait_request(self, filter_function: Optional[Callable] = None, callback_function: Optional[Callable] = None, timeout=None)
 |      Network.requestWillBeSent. To wait a special request filted by function, then run the callback_function(request_dict).
 |      
 |      Often used for HTTP packet capture:
 |      
 |          `await tab.wait_request(filter_function=lambda r: print(r), timeout=10)`
 |      
 |      WARNING: requestWillBeSent event fired do not mean the response is ready,
 |      should await tab.wait_request_loading(request_dict) or await tab.get_response(request_dict, wait_loading=True)
 |      WARNING: methods with prefix `wait_` the `timeout` default to None.
 |  
 |  async wait_request_loading(self, request_dict: Union[NoneType, dict, str], timeout=None)
 |      wait for the Network.loadingFinished event of given request id
 |  
 |  async wait_response(self, filter_function: Optional[Callable] = None, callback_function: Optional[Callable] = None, response_body: bool = True, timeout=Ellipsis)
 |      wait a special response filted by function, then run the callback_function.
 |      
 |      Sometimes the request fails to be sent, so use the `tab.wait_request` instead.
 |      if response_body:
 |          the non-null request_dict will contains response body.
 |  
 |  wait_response_context(self, filter_function: Optional[Callable] = None, callback_function: Optional[Callable] = None, response_body: bool = True, timeout=Ellipsis)
 |      Handler context for tab.wait_response.
 |      
 |          async with tab.wait_response_context(
 |                      filter_function=lambda r: tab.get_data_value(
 |                          r, 'params.response.url') == 'http://httpbin.org/get',
 |                      timeout=5,
 |              ) as r:
 |                  await tab.goto('http://httpbin.org/get')
 |                  result = await r
 |                  if result:
 |                      print(result['data'])
 |  
 |  async wait_tag(self, cssselector: str, max_wait_time: Optional[float] = None, interval: float = 1, timeout=Ellipsis) -> Optional[ichrome.base.Tag]
 |      Wait until the tag is ready or max_wait_time used up, sometimes it is more useful than wait loading.
 |      cssselector: css querying the Tag.
 |      interval: checking interval for while loop.
 |      max_wait_time: if time used up, return None.
 |      timeout: timeout seconds for sending a msg.
 |      
 |      If max_wait_time used up: return [].
 |      elif querySelectorAll runs failed, return None.
 |      else: return List[Tag]
 |      WARNING: methods with prefix `wait_` the `timeout` default to None.
 |  
 |  async wait_tag_click(self, cssselector: str, max_wait_time: Optional[float] = None, interval: float = 1, timeout=Ellipsis)
 |      wait the tag appeared and click it
 |  
 |  async wait_tags(self, cssselector: str, max_wait_time: Optional[float] = None, interval: float = 1, timeout=Ellipsis) -> List[ichrome.base.Tag]
 |      Wait until the tags is ready or max_wait_time used up, sometimes it is more useful than wait loading.
 |      cssselector: css querying the Tags.
 |      interval: checking interval for while loop.
 |      max_wait_time: if time used up, return [].
 |      timeout: timeout seconds for sending a msg.
 |      
 |      If max_wait_time used up: return [].
 |      elif querySelectorAll runs failed, return None.
 |      else: return List[Tag]
 |      WARNING: methods with prefix `wait_` the `timeout` default to None.
 |  
 |  ----------------------------------------------------------------------
 |  Class methods defined here:
 |  
 |  async repl(f_globals=None, f_locals=None) from builtins.type
 |      Give a simple way to debug your code with ichrome.
 |  
 |  ----------------------------------------------------------------------
 |  Static methods defined here:
 |  
 |  ensure_callback_type(_default_recv_callback)
 |      Ensure callback function has correct args
 |  
 |  get_smooth_steps(target_x, target_y, start_x, start_y, steps_count=30)
 |      smooth move steps
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties defined here:
 |  
 |  browser
 |  
 |  current_html
 |  
 |  current_title
 |  
 |  current_url
 |  
 |  frame_tree
 |  
 |  html
 |      `await tab.html`. return html from `document.documentElement.outerHTML`
 |  
 |  msg_id
 |  
 |  now
 |  
 |  status
 |  
 |  title
 |      await tab.title
 |  
 |  url
 |      Return the current url, `await tab.url`.
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors defined here:
 |  
 |  default_recv_callback
 |  
 |  ----------------------------------------------------------------------
 |  Data and other attributes defined here:
 |  
 |  __annotations__ = {'_DEFAULT_WS_KWARGS': typing.Dict}
 |  
 |  ----------------------------------------------------------------------
 |  Class methods inherited from GetValueMixin:
 |  
 |  check_error(name, result, value_path='error.message', **kwargs) from builtins.type
 |  
 |  ----------------------------------------------------------------------
 |  Static methods inherited from GetValueMixin:
 |  
 |  get_data_value(item, value_path: str = 'result.result.value', default=None)
 |      default value_path is for js response dict
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors inherited from GetValueMixin:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)

Help on module ichrome.base in ichrome:

NAME
    ichrome.base - Base utils and configs for ichrome

CLASSES
    builtins.object
        Tag
        TagNotFound

    class Tag(builtins.object)
     |  Tag(tagName, innerHTML, outerHTML, textContent, attributes, result)
     |  
     |  Handle the element's tagName, innerHTML, outerHTML, textContent, text, attributes, and the action result.
     |  
     |  Methods defined here:
     |  
     |  __init__(self, tagName, innerHTML, outerHTML, textContent, attributes, result)
     |      Initialize self.  See help(type(self)) for accurate signature.
     |  
     |  __repr__(self)
     |      Return repr(self).
     |  
     |  __str__(self)
     |      Return str(self).
     |  
     |  get(self, name, default=None)
     |      get the attribute of the tag
     |  
     |  to_dict(self)
     |      convert Tag object to dict
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)
    
    class TagNotFound(builtins.object)
     |  TagNotFound(*args, **kwargs)
     |  
     |  Same attributes like Tag, but return None
     |  
     |  Methods defined here:
     |  
     |  __bool__(self)
     |  
     |  __getattr__(self, name)
     |  
     |  __init__(self, *args, **kwargs)
     |      Initialize self.  See help(type(self)) for accurate signature.
     |  
     |  __repr__(self)
     |      Return repr(self).
     |  
     |  __str__(self)
     |      Return str(self).
     |  
     |  get(self, name, default=None)
     |  
     |  to_dict(self)
     |  
     |  ----------------------------------------------------------------------
     |  Data descriptors defined here:
     |  
     |  __dict__
     |      dictionary for instance variables (if defined)
     |  
     |  __weakref__
     |      list of weak references to the object (if defined)

FUNCTIONS
    clear_chrome_process(port=None, timeout=None, max_deaths=1, interval=0.5, host=None, proc_names=None)
        kill chrome processes, if port is not set, kill all chrome with --remote-debugging-port.
        set timeout to avoid running forever.
        set max_deaths and port, will return before timeout.

    async ensure_awaitable(result)
        avoid raising awaitable error while await something
    
    get_dir_size(path)
        return the dir space usage of the given dir path
    
    get_memory_by_port(port=9222, attr='uss', unit='MB', host=None, proc_names=None)
        get memory usage of chrome proc found with port and host.Only support local Daemon. `uss` is slower than `rss` but useful.
    
    get_proc(port=9222, proc_names=None, host=None) -> List[psutil.Process]
        find procs with given port and proc_names and host
    
    get_proc_by_regex(regex, proc_names=None, host_regex=None)
        find the procs with given proc_names and host_regex
    
    get_readable_dir_size(path)
        return the dir space usage of the given dir path with readable text.
    
    install_chromium(path=None, platform_name=None, x64=True, max_threads=5, version=None)
        download and unzip the portable chromium automatically

DATA
    CHROME_PROCESS_NAMES = {'chrome', 'chrome.exe', 'msedge.exe'}
    INF = inf
    List = typing.List
        A generic version of list.

    NotSet = Ellipsis
    logger = <Logger ichrome (INFO)>

FILE
    d:\github\ichrome\ichrome\base.py

Help on class AsyncChrome in module ichrome.async_utils:

class AsyncChrome(GetValueMixin)
 |  AsyncChrome(host: str = '127.0.0.1', port: int = 9222, timeout: int = None, retry: int = None)
 |  
 |  Method resolution order:
 |      AsyncChrome
 |      GetValueMixin
 |      builtins.object
 |  
 |  Methods defined here:
 |  
 |  async __aenter__(self)
 |  
 |  async __aexit__(self, *args)
 |  
 |  __del__(self)
 |  
 |  __getitem__(self, index: Union[int, str] = 0) -> Awaitable[Optional[ichrome.async_utils.AsyncTab]]
 |  
 |  __init__(self, host: str = '127.0.0.1', port: int = 9222, timeout: int = None, retry: int = None)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  __repr__(self)
 |      Return repr(self).
 |  
 |  __str__(self)
 |      Return str(self).
 |  
 |  async activate_tab(self, tab_id: Union[ichrome.async_utils.AsyncTab, str]) -> Union[str, bool]
 |  
 |  async check(self) -> bool
 |      Test http connection to cdp. `await self.check()`
 |  
 |  async close(self)
 |  
 |  async close_browser(self)
 |  
 |  async close_tab(self, tab_id: Union[ichrome.async_utils.AsyncTab, str]) -> Union[str, bool]
 |  
 |  async close_tabs(self, tab_ids: Union[NoneType, List[ichrome.async_utils.AsyncTab], List[str]] = None, *args) -> List[Union[str, bool]]
 |  
 |  async connect(self) -> bool
 |      await self.connect()
 |  
 |  connect_tab(self, index: Union[NoneType, int, str] = 0, auto_close: bool = False, flatten: bool = None)
 |      More easier way to init a connected Tab with `async with`.
 |      
 |      Got a connected Tab object by using `async with chrome.connect_tab(0) as tab::`
 |      
 |          index = 0 means the current tab.
 |          index = None means create a new tab.
 |          index = 'http://python.org' means create a new tab with url.
 |          index = 'F130D0295DB5879791AA490322133AFC' means the tab with this id.
 |      
 |          If auto_close is True: close this tab while exiting context.
 |  
 |  connect_tabs(self, *tabs) -> '_TabConnectionManager'
 |      async with chrome.connect_tabs([tab1, tab2]):.
 |      or
 |      async with chrome.connect_tabs(tab1, tab2)
 |  
 |  create_context(self, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None) -> 'BrowserContext'
 |      create a new Incognito BrowserContext
 |  
 |  async do_tab(self, tab_id: Union[ichrome.async_utils.AsyncTab, str], action: str) -> Union[str, bool]
 |  
 |  get_memory(self, attr='uss', unit='MB')
 |      Only support local Daemon. `uss` is slower than `rss` but useful.
 |  
 |  async get_server(self, api: str = '') -> torequests._py3_patch.NewResponse
 |  
 |  async get_tab(self, index: Union[int, str] = 0) -> Optional[ichrome.async_utils.AsyncTab]
 |      `await self.get_tab(1)` <=> await `(await self.get_tabs())[1]`
 |      If not exist, return None
 |      cdp url: /json
 |  
 |  async get_tabs(self, filt_page_type: bool = True) -> List[ichrome.async_utils.AsyncTab]
 |      `await self.get_tabs()`.
 |      cdp url: /json
 |  
 |  async get_version(self) -> dict
 |      `await self.get_version()`
 |      /json/version
 |  
 |  incognito_tab(self, url: str = 'about:blank', width: int = None, height: int = None, enableBeginFrameControl: bool = None, newWindow: bool = None, background: bool = None, flatten: bool = None, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None) -> 'IncognitoTabContext'
 |      create a new Incognito tab
 |  
 |  async init_browser_tab(self)
 |  
 |  async kill(self, timeout: Union[int, float] = None, max_deaths: int = 1) -> None
 |  
 |  async new_tab(self, url: str = '') -> Optional[ichrome.async_utils.AsyncTab]
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties defined here:
 |  
 |  browser
 |  
 |  meta
 |  
 |  ok
 |      await self.ok
 |  
 |  req
 |  
 |  server
 |      return like 'http://127.0.0.1:9222'
 |  
 |  tabs
 |      `await self.tabs`. tabs[0] is the current activated tab
 |  
 |  version
 |      `await self.version`
 |      {'Browser': 'Chrome/77.0.3865.90', 'Protocol-Version': '1.3', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36', 'V8-Version': '7.7.299.11', 'WebKit-Version': '537.36 (@58c425ba843df2918d9d4b409331972646c393dd)', 'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/browser/b5fbd149-959b-4603-b209-cfd26d66bdc1'}
 |  
 |  ----------------------------------------------------------------------
 |  Class methods inherited from GetValueMixin:
 |  
 |  check_error(name, result, value_path='error.message', **kwargs) from builtins.type
 |  
 |  ----------------------------------------------------------------------
 |  Static methods inherited from GetValueMixin:
 |  
 |  get_data_value(item, value_path: str = 'result.result.value', default=None)
 |      default value_path is for js response dict
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors inherited from GetValueMixin:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)

Help on class BrowserContext in module ichrome.async_utils:

class BrowserContext(builtins.object)
 |  BrowserContext(chrome: ichrome.async_utils.AsyncChrome, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None)
 |  
 |  Methods defined here:
 |  
 |  async __aenter__(self)
 |  
 |  async __aexit__(self, *_)
 |  
 |  __init__(self, chrome: ichrome.async_utils.AsyncChrome, disposeOnDetach: bool = True, proxyServer: str = None, proxyBypassList: str = None, originsWithUniversalNetworkAccess: List[str] = None)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  new_tab(self, url: str = 'about:blank', width: int = None, height: int = None, browserContextId: str = None, enableBeginFrameControl: bool = None, newWindow: bool = None, background: bool = None, auto_close: bool = False, flatten: bool = None) -> ichrome.async_utils._SingleTabConnectionManager
 |  
 |  ----------------------------------------------------------------------
 |  Readonly properties defined here:
 |  
 |  browser
 |  
 |  ----------------------------------------------------------------------
 |  Data descriptors defined here:
 |  
 |  __dict__
 |      dictionary for instance variables (if defined)
 |  
 |  __weakref__
 |      list of weak references to the object (if defined)

Help on class FetchBuffer in module ichrome.async_utils:

class FetchBuffer(EventBuffer)
 |  FetchBuffer(events: List[str], tab: ichrome.async_utils.AsyncTab, patterns: List[dict] = None, handleAuthRequests=False, timeout: Union[float, int] = None, maxsize: int = 0, kwargs: Any = None, callback: Callable = None)
 |  
 |  Enter and activate Fetch.enable, exit with Fetch.disable. Ensure only one FetchBuffer instance at the same moment.
 |  https://chromedevtools.github.io/devtools-protocol/tot/Fetch/
 |  
 |  Method resolution order:
 |      FetchBuffer
 |      EventBuffer
 |      asyncio.queues.Queue
 |      builtins.object
 |  
 |  Methods defined here:
 |  
 |  async __aenter__(self)
 |  
 |  async __aexit__(self, *_)
 |  
 |  __init__(self, events: List[str], tab: ichrome.async_utils.AsyncTab, patterns: List[dict] = None, handleAuthRequests=False, timeout: Union[float, int] = None, maxsize: int = 0, kwargs: Any = None, callback: Callable = None)
 |      Initialize self.  See help(type(self)) for accurate signature.
 |  
 |  async continueRequest(self, requestId: Union[str, dict], url: str = None, method: str = None, postData: str = None, headers: List[Dict[str, str]] = None, kwargs: dict = None, **_kwargs)
 |      Fetch.continueRequest. Continues the request, optionally modifying some of its parameters.
 |      
 |      :param requestId: An id the client received in requestPaused event.
 |      :type requestId: str
 |      :param url: If set, the request url will be modified in a way that's not observable by page., defaults to None
 |      :type url: str, optional
 |      :param method: If set, the request method is overridden., defaults to None
 |      :type method: str, optional
 |      :param postData: If set, overrides the post data in the request. (Encoded as a base64 string when passed over JSON), defaults to None
 |      :type postData: str, optional
 |      :param headers: If set, overrides the request headers., defaults to None
 |      :type headers: List[Dict[str, str]], optional
 |      :param kwargs: other params, defaults to None
 |      :type kwargs: dict, optional
 |  
 |  async continueWithAuth(self, requestId: Union[str, dict], response: str, username: str = None, password: str = None, kwargs: dict = None, **_kwargs)
 |      response: Allowed Values: Default, CancelAuth, ProvideCredentials
 |  
 |  async disable(self)
 |  
 |  async enable(self)
 |  
 |  ensure_request_id(self, data: Union[dict, str])
 |  
 |  async failRequest(self, requestId: Union[str, dict], errorReason: str, kwargs: dict = None, **_kwargs)
 |      Fetch.failRequest. Stop the request.
 |      
 |      Allowed ErrorReason:
 |      
 |      Failed, Aborted, TimedOut, AccessDenied, ConnectionClosed, ConnectionReset, ConnectionRefused, ConnectionAborted, ConnectionFailed, NameNotResolved, InternetDisconnected, AddressUnreachable, BlockedByClient, BlockedByResponse
 |  
 |  async fulfillRequest(self, requestId: Union[str, dict], responseCode: int, responseHeaders: List[Dict[str, str]] = None, binaryResponseHeaders: str = None, body: Union[str, bytes] = None, responsePhrase: str = None, kwargs: dict = None, **_kwargs)
 |      Fetch.fulfillRequest. Provides response to the request.
 |      
 |      :param requestId: An id the client received in requestPaused event.
 |      :type requestId: str
 |      :param responseCode: An HTTP response code.
 |      :type responseCode: int
 |      :param responseHeaders: Response headers, defaults to None
 |      :type responseHeaders: List[Dict[str, str]], optional
 |      :param binaryResponseHeaders: Alternative way of specifying response headers as a 
