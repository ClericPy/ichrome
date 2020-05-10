# -*- coding: utf-8 -*-
import argparse
import asyncio
import sys
from pathlib import Path

from ichrome import ChromeDaemon, ChromeWorkers, __version__, logger


def main():
    usage = '''
    All the unknown args will be appended to extra_config as chrome original args.

Demo:
    > python -m ichrome --host=127.0.0.1 --window-size=1212,1212 --incognito
    > ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': '127.0.0.1', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': False, 'start_url': 'about:blank', 'extra_config': ['--window-size=1212,1212', '--incognito'], 'max_deaths': 1, 'timeout': 2}

Other operations:
    1. kill local chrome process with given port:
        python -m ichrome -s 9222
    2. clear user_data_dir path (remove the folder and files):
        python -m ichrome --clear
        python -m ichrome --clean
    2. show ChromeDaemon.__doc__:
        python -m ichrome --doc
'''
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument("-V",
                        "--version",
                        help="ichrome version info",
                        action="store_true")
    parser.add_argument(
        "-c",
        "--chrome_path",
        help=
        "chrome executable file path, default to null for automatic searching",
        default="")
    parser.add_argument("--host",
                        help="--remote-debugging-address, default to 127.0.0.1",
                        default="127.0.0.1")
    parser.add_argument("-p",
                        "--port",
                        help="--remote-debugging-port, default to 9222",
                        default=9222,
                        type=int)
    parser.add_argument(
        "--headless",
        help="--headless and --hide-scrollbars, default to False",
        default=False,
        action="store_true")
    parser.add_argument(
        "-s",
        "--shutdown",
        help="shutdown the given port, only for local running chrome",
        type=int)
    parser.add_argument(
        "--user_agent",
        help=
        "--user-agen, default to 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36'",
        default="")
    parser.add_argument("--proxy",
                        help="--proxy-server, default to None",
                        default="")
    parser.add_argument(
        "--user_data_dir",
        help=
        "user_data_dir to save the user data, default to ~/ichrome_user_data",
        default=Path.home() / 'ichrome_user_data')
    parser.add_argument(
        "--disable_image",
        help="disable image for loading performance, default to False",
        action="store_true")
    parser.add_argument(
        "--start_url",
        help="start url while launching chrome, default to about:blank",
        default="about:blank")
    parser.add_argument(
        "--max_deaths",
        help=
        "max deaths in 5 secs, auto restart `max_deaths` times if crash fast in 5 secs. default to 1 for without auto-restart",
        default=1,
        type=int)
    parser.add_argument(
        "--timeout",
        help="timeout to connect the remote server, default to 1 for localhost",
        default=1,
        type=int)
    parser.add_argument(
        "--workers",
        help=
        "the number of worker processes with auto-increment port, default to 1",
        default=1,
        type=int)
    parser.add_argument(
        "--proc_check_interval",
        dest='proc_check_interval',
        help="check chrome process alive every interval seconds",
        default=5,
        type=int)
    parser.add_argument("--clean",
                        "--clear",
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
    args, extra_config = parser.parse_known_args()
    if args.version:
        print(__version__)
        return
    if args.shutdown:
        logger.setLevel(1)
        ChromeDaemon.clear_chrome_process(args.shutdown,
                                          max_deaths=args.max_deaths)
        return
    if args.clean:
        logger.setLevel(1)
        ChromeDaemon.clear_user_dir(args.user_data_dir)
        return
    if args.doc:
        logger.setLevel(1)
        print(ChromeDaemon.__doc__)
        return
    kwargs = {}
    kwargs.update(
        chrome_path=args.chrome_path,
        host=args.host,
        headless=args.headless,
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
    asyncio.run(ChromeWorkers.run_chrome_workers(args, kwargs))


if __name__ == "__main__":
    sys.exit(main())
