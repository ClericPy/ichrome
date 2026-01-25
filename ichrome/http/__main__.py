#!/usr/bin/env python3
"""
Main entry point for ichrome.http module.

This allows running the HTTP server via: python -m ichrome.http

Examples:
    python -m ichrome.http --host 127.0.0.1 --port 8080 --workers 1
"""

import argparse
import asyncio
import json
from pathlib import Path

from aiohttp import web

from ..logs import logger
from ..pool import ChromeEngine
from .app import API_DOCS, create_app
from ..schemas.http_schema import ChromeConfig, ServerConfig


def main():
    parser = argparse.ArgumentParser(
        description="ichrome http server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"API Documentation:\n{json.dumps(API_DOCS, indent=2, ensure_ascii=False)}",
    )
    # Server Config
    server_group = parser.add_argument_group("Server Configuration")
    server_group.add_argument("--host", default="127.0.0.1", help="server host")
    server_group.add_argument("--port", type=int, default=8080, help="server port")

    # Chrome Config
    chrome_group = parser.add_argument_group("Chrome Configuration")
    chrome_group.add_argument(
        "-w",
        "--workers",
        "--workers-amount",
        type=int,
        default=1,
        dest="workers_amount",
        help="chrome workers amount",
    )
    chrome_group.add_argument(
        "--max-concurrent-tabs",
        type=int,
        default=5,
        dest="max_concurrent_tabs",
        help="max concurrent tabs per worker",
    )
    chrome_group.add_argument(
        "-sp",
        "--start-port",
        type=int,
        default=9345,
        dest="start_port",
        help="chrome start port",
    )
    chrome_group.add_argument(
        "--headless",
        type=int,
        default=1,
        help="chrome headless mode (1 for True, 0 for False, default: 1)",
    )
    chrome_group.add_argument(
        "--window-size",
        type=str,
        default="1920,1080",
        help="chrome window size, format: WIDTH,HEIGHT (default: 1920,1080)",
    )
    chrome_group.add_argument(
        "-cp",
        "--chrome-path",
        default="",
        dest="chrome_path",
        help="chrome executable file path",
    )
    chrome_group.add_argument(
        "-U",
        "--user-data-dir",
        default="",
        dest="user_data_dir",
        help="user_data_dir to save user data",
    )
    chrome_group.add_argument(
        "--disable-image",
        action="store_true",
        dest="disable_image",
        help="disable image for loading performance",
    )
    chrome_group.add_argument(
        "--restart-every",
        type=int,
        default=8 * 60,
        dest="restart_every",
        help="restart chrome worker every N seconds (default: 480)",
    )
    chrome_group.add_argument(
        "--default-cache-size",
        type=int,
        default=100 * 1024**2,
        dest="default_cache_size",
        help="default disk cache size in bytes (default: 100MB)",
    )
    chrome_group.add_argument(
        "--extra-config",
        nargs="*",
        default=[],
        help="extra chrome flags, e.g. --extra-config --proxy-server=http://127.0.0.1:1080",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="load config from JSON file to overwrite arguments. If the file does not exist, a default config file will be created.",
    )

    args = parser.parse_args()

    server_config = ServerConfig(host=args.host, port=args.port)
    headless = bool(args.headless)
    chrome_config = ChromeConfig(
        workers_amount=args.workers_amount,
        max_concurrent_tabs=args.max_concurrent_tabs,
        start_port=args.start_port,
        headless=headless,
        chrome_path=args.chrome_path,
        user_data_dir=args.user_data_dir,
        disable_image=args.disable_image,
        restart_every=args.restart_every,
        default_cache_size=args.default_cache_size,
        window_size=args.window_size,
        extra_config=args.extra_config,
    )

    if args.config:
        config_path = Path(args.config)
        if config_path.is_file():
            config_data = json.loads(config_path.read_text())
            if "server" in config_data:
                server_config.update(config_data["server"])
            if "chrome" in config_data:
                chrome_config.update(config_data["chrome"])
        else:
            # Create default config file if it doesn't exist
            from dataclasses import asdict

            default_config = {
                "server": asdict(server_config),
                "chrome": asdict(chrome_config),
            }
            config_path.write_text(json.dumps(default_config, indent=4))
            logger.info(
                f"Config file not found, created default config at: {args.config}"
            )
            return

    async def run_server():
        async with ChromeEngine(**chrome_config.to_engine_params()) as engine:
            app = await create_app(engine, api_prefix=server_config.api_prefix)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, server_config.host, server_config.port)
            logger.info(
                f"HTTP server starting on http://{server_config.host}:{server_config.port}, "
                f"visit http://{server_config.host}:{server_config.port}{server_config.api_prefix.rstrip('/')}/docs for API documentation and examples."
            )
            await site.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                try:
                    await runner.cleanup()
                except Exception:
                    pass

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
