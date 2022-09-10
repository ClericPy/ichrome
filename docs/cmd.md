# Command Line

> Be used for launching a chrome daemon process. The unhandled args will be treated as chrome raw args and appended to extra_config list.
> 
> [Chromium Command Line Args List](https://peter.sh/experiments/chromium-command-line-switches/)

Shutdown Chrome process with the given port
```bash
λ python3 -m ichrome -s 9222
2018-11-27 23:01:59 DEBUG [ichrome] base.py(329): kill chrome.exe --remote-debugging-port=9222
2018-11-27 23:02:00 DEBUG [ichrome] base.py(329): kill chrome.exe --remote-debugging-port=9222
```
Launch a Chrome daemon process
```bash
λ python3 -m ichrome -p 9222 --start_url "http://bing.com" --disable_image
2018-11-27 23:03:57 INFO  [ichrome] __main__.py(69): ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': 'localhost', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': True, 'start_url': 'http://bing.com', 'extra_config': '', 'max_deaths': 1, 'timeout': 2}
```
Crawl the given URL, output the HTML DOM
```bash
λ python3 -m ichrome --crawl --headless --timeout=2 http://api.ipify.org/
<html><head></head><body><pre style="word-wrap: break-word; white-space: pre-wrap;">38.143.68.66</pre></body></html>
```
To use default user dir (ignore ichrome user-dir settings)
> ensure the existing Chromes get closed
```bash
λ python -m ichrome -U null
```

Details:

    $ python3 -m ichrome --help

```
usage:
    All the unknown args will be appended to extra_config as chrome original args.
    Maybe you can have a try by typing: `python3 -m ichrome --try`

Demo:
    > python -m ichrome -H 127.0.0.1 -p 9222 --window-size=1212,1212 --incognito
    > ChromeDaemon cmd args: port=9222, {'chrome_path': '', 'host': '127.0.0.1', 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': WindowsPath('C:/Users/root/ichrome_user_data'), 'disable_image': False, 'start_url': 'about:blank', 'extra_config': ['--window-size=1212,1212', '--incognito'], 'max_deaths': 1, 'timeout':1, 'proc_check_interval': 5, 'debug': False}

    > python -m ichrome
    > ChromeDaemon cmd args: port=9222, {'chrome_path': '', 'host': '127.0.0.1', 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': WindowsPath('C:/Users/root/ichrome_user_data'), 'disable_image': False, 'start_url': 'about:blank', 'extra_config': [], 'max_deaths': 1, 'timeout': 1, 'proc_check_interval': 5, 'debug': False}

Other operations:
    1. kill local chrome process with given port:
        python -m ichrome -s 9222
        python -m ichrome -k 9222
    2. clear user_data_dir path (remove the folder and files):
        python -m ichrome --clear
        python -m ichrome --clean
        python -m ichrome -C -p 9222
    3. show ChromeDaemon.__doc__:
        python -m ichrome --doc
    4. crawl the URL, output the HTML DOM:
        python -m ichrome --crawl --headless --timeout=2 http://myip.ipip.net/

optional arguments:
  -h, --help            show this help message and exit
  -v, -V, --version     ichrome version info
  -c CONFIG, --config CONFIG
                        load config dict from JSON file of given path
  -cp CHROME_PATH, --chrome-path CHROME_PATH, --chrome_path CHROME_PATH
                        chrome executable file path, default to null for
                        automatic searching
  -H HOST, --host HOST  --remote-debugging-address, default to 127.0.0.1
  -p PORT, --port PORT  --remote-debugging-port, default to 9222
  --headless            --headless and --hide-scrollbars, default to False
  -s SHUTDOWN, -k SHUTDOWN, --shutdown SHUTDOWN
                        shutdown the given port, only for local running chrome
  -A USER_AGENT, --user-agent USER_AGENT, --user_agent USER_AGENT
                        --user-agent, default to Chrome PC: Mozilla/5.0
                        (Linux; Android 6.0; Nexus 5 Build/MRA58N)
                        AppleWebKit/537.36 (KHTML, like Gecko)
                        Chrome/83.0.4103.106 Mobile Safari/537.36
  -x PROXY, --proxy PROXY
                        --proxy-server, default to None
  -U USER_DATA_DIR, --user-data-dir USER_DATA_DIR, --user_data_dir USER_DATA_DIR
                        user_data_dir to save user data, default to
                        ~/ichrome_user_data
  --disable-image, --disable_image
                        disable image for loading performance, default to
                        False
  -url START_URL, --start-url START_URL, --start_url START_URL
                        start url while launching chrome, default to
                        about:blank
  --max-deaths MAX_DEATHS, --max_deaths MAX_DEATHS
                        restart times. default to 1 for without auto-restart
  --timeout TIMEOUT     timeout to connect the remote server, default to 1 for
                        localhost
  -w WORKERS, --workers WORKERS
                        the number of worker processes, default to 1
  --proc-check-interval PROC_CHECK_INTERVAL, --proc_check_interval PROC_CHECK_INTERVAL
                        check chrome process alive every interval seconds
  --crawl               crawl the given URL, output the HTML DOM
  -C, --clear, --clear  clean user_data_dir
  --doc                 show ChromeDaemon.__doc__
  --debug               set logger level to DEBUG
  -K, --killall         killall chrome launched local with --remote-debugging-
                        port
  -t, --try, --demo, --repl
                        Have a try for ichrome with repl mode.
  -tc, --try-connection, --repl-connection
                        Have a try for ichrome with repl mode (connect to a launched chrome).
```
