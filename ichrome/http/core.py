"""
HTTP API server for ichrome, exposing ChromeEngine's functionalities.

Usage:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1
"""

from aiohttp import web

from ..pool import ChromeEngine
from .controller import HttpController
from .doc import API_DOCS

__all__ = ["API_DOCS", "create_app"]


async def create_app(engine: ChromeEngine):
    app = web.Application()
    controller = HttpController(engine)
    app.router.add_route("*", "/download", controller.download)
    app.router.add_route("*", "/preview", controller.preview)
    app.router.add_route("*", "/snapshot", controller.snapshot)
    app.router.add_route("*", "/js", controller.js)
    app.router.add_route("POST", "/do", controller.do)
    app.router.add_route("GET", "/docs", controller.docs)
    return app
