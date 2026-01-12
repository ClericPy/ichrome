#!/usr/bin/env python3
"""
Main entry point for ichrome.http module.

This allows running the HTTP server via: python -m ichrome.http

Examples:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1
"""

import argparse
import asyncio
import json

from aiohttp import web

from ..logs import logger
from ..pool import ChromeEngine
from .core import API_DOCS, create_app


def main():
    parser = argparse.ArgumentParser(
        description="ichrome http server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"API Documentation:\n{json.dumps(API_DOCS, indent=2, ensure_ascii=False)}",
    )
    parser.add_argument("--host", default="0.0.0.0", help="server host")
    parser.add_argument("--port", type=int, default=8080, help="server port")
    parser.add_argument("--workers", type=int, default=1, help="chrome workers amount")
    parser.add_argument(
        "--headless",
        type=int,
        default=1,
        help="chrome headless mode (1 for True, 0 for False)",
    )
    args = parser.parse_args()

    async def run_server():
        async with ChromeEngine(
            workers_amount=args.workers, headless=bool(args.headless)
        ) as engine:
            app = await create_app(engine)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, args.host, args.port)
            logger.info(
                f"HTTP server starting on http://{args.host}:{args.port}, "
                f"visit http://{args.host}:{args.port}/docs for API documentation and examples."
            )
            await site.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            finally:
                await runner.cleanup()

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
