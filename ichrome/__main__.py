# -*- coding: utf-8 -*-
import argparse
import asyncio
import re
import sys
from pathlib import Path

from ichrome import ChromeDaemon, ChromeWorkers, __version__, logger
from ichrome.base import get_readable_dir_size, install_chromium


def main():
    usage = '''
    All the unknown args will be appended to extra_config as chrome original args.

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
        python -m ichrome --crawl --timeout=2 http://myip.ipip.net/
'''
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument("-v",
                        "-V",
                        "--version",
                        help="ichrome version info",
                        action="store_true")
    parser.add_argument("-c",
                        "--config",
                        help="load config dict from JSON file of given path",
                        default="")
    parser.add_argument(
        "-cp",
        "--chrome-path",
        "--chrome_path",
        help="chrome executable file path, default to null(automatic searching)",
        default="")
    parser.add_argument("-H",
                        "--host",
                        help="--remote-debugging-address, default to 127.0.0.1",
                        default="127.0.0.1")
    parser.add_argument("-p",
                        "--port",
                        help="--remote-debugging-port, default to 9222",
                        default=argparse.SUPPRESS,
                        type=int)
    parser.add_argument("--log-level",
                        "--log_level",
                        help="logger level, will be overwrited by --debug",
                        default=argparse.SUPPRESS)
    parser.add_argument(
        "--headless",
        help="--headless and --hide-scrollbars, default to False",
        default=argparse.SUPPRESS,
        action="store_true")
    parser.add_argument(
        "-s",
        "-k",
        "--shutdown",
        help="shutdown the given port, only for local running chrome",
        type=int)
    parser.add_argument(
        "-A",
        "--user-agent",
        "--user_agent",
        help=f"--user-agent, default to Chrome PC: {ChromeDaemon.PC_UA}",
        default="")
    parser.add_argument("-x",
                        "--proxy",
                        help="--proxy-server, default to None",
                        default="")
    parser.add_argument(
        "-U",
        "--user-data-dir",
        "--user_data_dir",
        help="user_data_dir to save user data, default to ~/ichrome_user_data",
        default=Path.home() / 'ichrome_user_data')
    parser.add_argument(
        "--disable-image",
        "--disable_image",
        help="disable image for loading performance, default to False",
        action="store_true")
    parser.add_argument(
        "-url",
        "--start-url",
        "--start_url",
        help="start url while launching chrome, default to about:blank",
        default="about:blank")
    parser.add_argument(
        "--max-deaths",
        "--max_deaths",
        help="restart times. default to 1 for without auto-restart",
        default=1,
        type=int)
    parser.add_argument(
        "--timeout",
        help="timeout to connect the remote server, default to 1 for localhost",
        default=1,
        type=int)
    parser.add_argument("-w",
                        "--workers",
                        help="the number of worker processes, default to 1",
                        default=1,
                        type=int)
    parser.add_argument(
        "--proc-check-interval",
        "--proc_check_interval",
        dest='proc_check_interval',
        help="check chrome process alive every interval seconds",
        default=5,
        type=int)
    parser.add_argument("-crawl",
                        "--crawl",
                        help="crawl the given URL, output the HTML DOM",
                        default=False,
                        action="store_true")
    parser.add_argument("-C",
                        "--clear",
                        "--clean",
                        dest='clean',
                        help="clean user_data_dir",
                        default=False,
                        action="store_true")
    parser.add_argument("--doc",
                        dest='doc',
                        help="show ChromeDaemon.__doc__",
                        default=False,
                        action="store_true")
    parser.add_argument("--debug",
                        dest='debug',
                        help="set logger level to DEBUG",
                        default=False,
                        action="store_true")
    parser.add_argument("-cc",
                        "--clear-cache",
                        "--clear_cache",
                        help="clear cache for given port, port default to 9222",
                        default=False,
                        action="store_true")
    parser.add_argument(
        "-K",
        "--killall",
        help="killall chrome launched local with --remote-debugging-port",
        default=False,
        action="store_true")
    parser.add_argument("--install",
                        help="download chromium and unzip it to given path",
                        default="")
    args, extra_config = parser.parse_known_args()

    if args.version:
        print(__version__)
        return
    if args.install:
        return install_chromium(args.install)
    if args.config:
        path = Path(args.config)
        if not (path.is_file() and path.exists()):
            logger.error(f'config file not found: {path}')
            return
        import json
        kwargs = json.loads(path.read_text())
        start_port = kwargs.pop('port', 9222)
        workers = kwargs.pop('workers', 1)
        asyncio.run(
            ChromeWorkers.run_chrome_workers(start_port, workers, kwargs))
        return
    if args.shutdown:
        logger.setLevel(1)
        ChromeDaemon.clear_chrome_process(args.shutdown,
                                          max_deaths=args.max_deaths)
        return
    if args.killall:
        logger.setLevel(1)
        ChromeDaemon.clear_chrome_process(None, max_deaths=args.max_deaths)
        return
    if args.clean:
        logger.setLevel(1)
        ChromeDaemon.clear_user_dir(args.user_data_dir,
                                    port=getattr(args, 'port', None))
        return
    if args.doc:
        logger.setLevel(1)
        print(ChromeDaemon.__doc__)
        return

    kwargs = {}
    kwargs.update(
        chrome_path=args.chrome_path,
        host=args.host,
        headless=getattr(args, 'headless', False),
        user_agent=args.user_agent,
        proxy=args.proxy,
        user_data_dir=args.user_data_dir,
        disable_image=args.disable_image,
        start_url=args.start_url,
        extra_config=extra_config,
        max_deaths=args.max_deaths,
        timeout=args.timeout,
        proc_check_interval=args.proc_check_interval,
        debug=args.debug,
    )
    log_level = getattr(args, 'log_level', None)
    if log_level:
        logger.setLevel(log_level)
    if kwargs['start_url'] == 'about:blank' or not kwargs['start_url']:
        # reset start_url from extra_config
        for config in kwargs['extra_config']:
            if re.match('^https?://', config):
                kwargs['start_url'] = config
                kwargs['extra_config'].remove(config)
                break

    if '--dump-dom' in extra_config or args.crawl:
        logger.setLevel(60)
        from .debugger import crawl_once
        if kwargs['start_url'] == 'about:blank' or not kwargs['start_url']:
            kwargs['start_url'] = kwargs['extra_config'].pop(0)
        if kwargs['start_url'] != 'about:blank' and not kwargs[
                'start_url'].startswith('http'):
            kwargs['start_url'] = 'http://' + kwargs['start_url']
        kwargs['headless'] = getattr(args, 'headless', True)
        kwargs['disable_image'] = True
        kwargs['timeout'] = max([5, args.timeout])
        print(asyncio.run(crawl_once(**kwargs)), flush=True)
    elif args.clear_cache:
        from .debugger import clear_cache_handler
        kwargs['headless'] = getattr(args, 'headless', True)
        port = kwargs.get('port') or 9222
        main_user_dir = ChromeDaemon._ensure_user_dir(kwargs['user_data_dir'])
        port_user_dir = main_user_dir / f"chrome_{port}"
        print(
            f'Clearing cache(port={port}): {get_readable_dir_size(port_user_dir)}'
        )
        asyncio.run(clear_cache_handler(**kwargs))
        print(
            f'Cleared  cache(port={port}): {get_readable_dir_size(port_user_dir)}'
        )
    else:
        start_port = getattr(args, 'port', 9222)
        asyncio.run(
            ChromeWorkers.run_chrome_workers(start_port, args.workers, kwargs))


if __name__ == "__main__":
    sys.exit(main())
