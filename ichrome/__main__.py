import argparse
import sys

from ichrome import ChromeDaemon, __version__, logger


def main():
    """handle ichrome command line args
    chrome_path=None,
    host="localhost",
    port=9222,
    headless=False,
    user_agent=None,
    proxy=None,
    user_data_dir=None,
    disable_image=False,
    start_url="about:blank",
    extra_config=None,
    max_deaths=1,
    timeout=2
    """
    usage = '''
    All the unknown args will be append to extra_config.
Demo:
    > python -m ichrome --host=127.0.0.1 --window-size=1212,1212 --incognito
    > ChromeDaemon cmd args: {'daemon': True, 'block': True, 'chrome_path': '', 'host': '127.0.0.1', 'port': 9222, 'headless': False, 'user_agent': '', 'proxy': '', 'user_data_dir': None, 'disable_image': False, 'start_url': 'about:blank', 'extra_config': ['--window-size=1212,1212', '--incognito'], 'max_deaths': 1, 'timeout': 2}
'''
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument(
        "-V",
        "--version",
        help="show ichrome version info",
        action="store_true")
    parser.add_argument("-c", "--chrome_path", help="chrome_path", default="")
    parser.add_argument("--host", help="host", default="localhost")
    parser.add_argument("-p", "--port", help="port", default=9222, type=int)
    parser.add_argument(
        "--headless", help="is_headless", default=False, action="store_true")
    parser.add_argument("-s", "--shutdown", help="shutdown the port", type=int)
    parser.add_argument("--user_agent", help="user_agent", default="")
    parser.add_argument("--proxy", help="proxy", default="")
    parser.add_argument("--user_data_dir", help="user_data_dir", default=None)
    parser.add_argument(
        "--disable_image", help="disable_image", action="store_true")
    parser.add_argument("--start_url", help="start_url", default="about:blank")
    parser.add_argument("--max_deaths", help="max_deaths", default=1, type=int)
    parser.add_argument("--timeout", help="timeout", default=2, type=int)
    args, extra_config = parser.parse_known_args()
    if args.version:
        print(__version__)
        return
    if args.shutdown:
        logger.setLevel(1)
        ChromeDaemon.clear_chrome_process(
            args.shutdown, max_deaths=args.max_deaths)
        return
    kwargs = {"daemon": True, "block": True}
    kwargs.update(
        chrome_path=args.chrome_path,
        host=args.host,
        port=args.port,
        headless=args.headless,
        user_agent=args.user_agent,
        proxy=args.proxy,
        user_data_dir=args.user_data_dir,
        disable_image=args.disable_image,
        start_url=args.start_url,
        extra_config=extra_config,
        max_deaths=args.max_deaths,
        timeout=args.timeout,
    )
    logger.info("ChromeDaemon cmd args: %s" % kwargs)
    ChromeDaemon(**kwargs)


if __name__ == "__main__":
    sys.exit(main())
