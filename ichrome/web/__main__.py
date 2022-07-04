from argparse import ArgumentParser
from pathlib import Path
from .config import Config
import json


def main():
    usage = r'''
>>> python -m ichrome.web

view urls with your browser

http://127.0.0.1:8080/chrome/screenshot?url=http://bing.com

http://127.0.0.1:8080/chrome/download?url=http://bing.com

http://127.0.0.1:8080/chrome/preview?url=http://bing.com
    '''
    parser = ArgumentParser(usage=usage)
    parser.add_argument("-c",
                        "--config",
                        help="load config dict from JSON file "
                        "of given path to overwrite other args,"
                        " default Config JSON: %s" % json.dumps(Config),
                        default="")
    parser.add_argument("-H",
                        "--host",
                        help="uvicorn host, default to 127.0.0.1",
                        default="127.0.0.1")
    parser.add_argument("-p",
                        "--port",
                        help="uvicorn port, default to 8080",
                        default=8080,
                        type=int)
    parser.add_argument("--prefix",
                        help="Fastapi.include_router.prefix",
                        default='/chrome')
    parser.add_argument("-sp",
                        "--start-port",
                        help="ChromeAPIRouterArgs.start_port",
                        default=9345,
                        dest='start_port',
                        type=int)
    parser.add_argument("-w",
                        "--workers",
                        "--workers-amount",
                        help="ChromeAPIRouterArgs.workers_amount",
                        default=1,
                        dest='workers_amount',
                        type=int)
    parser.add_argument("--max-concurrent-tabs",
                        help="ChromeAPIRouterArgs.max_concurrent_tabs",
                        default=1,
                        dest='max_concurrent_tabs',
                        type=int)
    parser.add_argument("--restart-every",
                        help="ChromeWorker.RESTART_EVERY",
                        default=8 * 60,
                        dest='RESTART_EVERY',
                        type=int)
    parser.add_argument("--default-cache-size",
                        help="ChromeWorker.DEFAULT_CACHE_SIZE",
                        default=8 * 60,
                        dest='DEFAULT_CACHE_SIZE',
                        type=int)
    parser.add_argument(
        "-cp",
        "--chrome-path",
        "--chrome_path",
        help="chrome executable file path, default to null(automatic searching)",
        default="")
    parser.add_argument("--disable-headless",
                        help="disable --headless arg for chrome",
                        default=False,
                        dest='disable_headless',
                        action="store_true")
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
    args = parser.parse_args()
    if args.config:
        path = Path(args.config)
        if not (path.is_file()):
            raise FileNotFoundError(path.as_posix())
        Config.update(json.loads(path.read_text()))
    else:
        Config['UvicornArgs']['host'] = args.host
        Config['UvicornArgs']['port'] = args.port
        Config['IncludeRouterArgs']['prefix'] = args.prefix
        if args.disable_headless:
            Config['ChromeAPIRouterArgs']['headless'] = False
        Config['ChromeAPIRouterArgs']['start_port'] = args.start_port
        Config['ChromeAPIRouterArgs']['workers_amount'] = args.workers_amount
        Config['ChromeAPIRouterArgs'][
            'max_concurrent_tabs'] = args.max_concurrent_tabs
        Config['ChromeWorkerArgs']['RESTART_EVERY'] = args.RESTART_EVERY
        Config['ChromeWorkerArgs'][
            'DEFAULT_CACHE_SIZE'] = args.DEFAULT_CACHE_SIZE
    from .http import start_server
    start_server()


if __name__ == "__main__":
    main()
