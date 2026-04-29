"""
HTTP API server for ichrome, exposing ChromeEngine's functionalities.

Usage:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1
"""

import asyncio
from typing import Any

from aiohttp import web

from ..logs import logger
from ..pool import ChromeEngine
from ..schemas.http_schema import ChromeConfig, ServerConfig
from .controller import HttpController
from .doc import API_DOCS

__all__ = ["API_DOCS", "HttpServer", "create_app"]


def _register_routes(app: web.Application, controller: HttpController, api_prefix: str) -> None:
    """Register controller routes onto the app with the given prefix."""
    prefix = "/" + api_prefix.strip("/")
    if prefix == "/":
        prefix = ""
    for method, path, handler in controller.routers:
        app.router.add_route(method, prefix + path, handler)


async def create_app(engine: ChromeEngine, api_prefix: str = "/"):
    """Backward-compatible entry: create an aiohttp app with default HttpController."""
    controller = HttpController(engine, api_prefix=api_prefix)
    app = web.Application()
    _register_routes(app, controller, api_prefix)
    return app


class HttpServer:
    """HTTP server that manages ChromeEngine lifecycle and HttpController routing."""

    controller_class: type = HttpController

    def __init__(
        self,
        chrome_config: ChromeConfig,
        server_config: ServerConfig | None = None,
    ):
        self.chrome_config = chrome_config
        self.server_config = server_config or ServerConfig()
        self._engine: ChromeEngine | None = None

    async def create_app(self) -> web.Application:
        if self._engine is None:
            raise RuntimeError("HttpServer is not started, use 'async with HttpServer(...)' first")
        controller = self.controller_class(
            self._engine, api_prefix=self.server_config.api_prefix
        )
        app = web.Application()
        _register_routes(app, controller, self.server_config.api_prefix)
        return app

    async def __aenter__(self) -> "HttpServer":
        engine = ChromeEngine(**self.chrome_config.to_engine_params())
        await engine.__aenter__()
        self._engine = engine
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._engine is not None:
            await self._engine.__aexit__(*exc)
            self._engine = None

    async def run_server(self) -> None:
        """Run the HTTP server until cancelled.

        Must be called inside ``async with HttpServer(...)``.
        """
        app = await self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(
            runner, self.server_config.host, self.server_config.port
        )
        logger.info(
            f"HTTP server starting on http://{self.server_config.host}:{self.server_config.port}, "
            f"visit http://{self.server_config.host}:{self.server_config.port}"
            f"{self.server_config.api_prefix.rstrip('/')}/docs for API documentation and examples."
        )
        await site.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()
