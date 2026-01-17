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


async def create_app(engine: ChromeEngine, api_prefix: str = "/"):
    app = web.Application()
    controller = HttpController(engine, api_prefix=api_prefix)
    prefix = "/" + api_prefix.strip("/")
    if prefix == "/":
        prefix = ""

    routes = [
        ("*", "/download", controller.download),
        ("*", "/screenshot", controller.screenshot),
        ("*", "/js", controller.js),
        ("*", "/do", controller.do),
        ("GET", "/docs", controller.docs),
    ]
    for method, path, handler in routes:
        app.router.add_route(method, prefix + path, handler)
    return app
