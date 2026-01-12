"""
HTTP API server for ichrome, exposing ChromeEngine's functionalities.

Usage:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1

All API endpoints:
    - GET/POST /download - Download page source
    - GET/POST /preview - Preview page HTML
    - GET/POST /snapshot - Take screenshot (returns image bytes)
    - GET /docs - API documentation
"""

from typing import Any, Dict

from aiohttp import web
from morebuiltins.utils import format_error

from ..logs import logger
from ..pool import ChromeEngine
from .schemas import DownloadArgs, PreviewArgs, Response, SnapshotArgs

# API documentation metadata
API_DOCS = {
    "description": "ichrome HTTP API via aiohttp",
    "response_schema": {
        "code": "int (0 for success, 1 for error)",
        "data": "any (result data on success)",
        "msg": "str (error message on error)",
    },
    "endpoints": [
        {
            "route": "/download",
            "methods": ["GET", "POST"],
            "description": "Download page source or specific element HTML",
            "parameters": {
                "url": "str (required)",
                "css_selector": "str (optional, element to extract)",
                "wait_tag": "str (optional, wait before returning)",
                "timeout": "float (default: 5.0)",
                "cookies": "dict (optional)",
                "user_agent": "str (optional)",
                "extra_headers": "dict (optional)",
                "incognito_args": "dict (optional)",
            },
            "demo_url": "http://127.0.0.1:8080/download?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/download",
                    "body": {"url": "http://example.com", "timeout": 10},
                },
            ],
        },
        {
            "route": "/preview",
            "methods": ["GET", "POST"],
            "description": "Preview page HTML (returns text/html directly)",
            "parameters": {
                "url": "str (required)",
                "wait_tag": "str (optional)",
                "timeout": "float (default: 5.0)",
            },
            "demo_url": "http://127.0.0.1:8080/preview?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/preview?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/preview",
                    "body": {"url": "http://example.com"},
                },
            ],
        },
        {
            "route": "/snapshot",
            "methods": ["GET", "POST"],
            "description": "Take screenshot (returns image bytes directly)",
            "parameters": {
                "url": "str (required)",
                "css_selector": "str (optional)",
                "scale": "float (default: 1.0)",
                "image_format": "str (png/jpeg, default: png)",
                "quality": "int (1-100, default: 100)",
                "from_surface": "bool (default: True)",
                "capture_beyond_viewport": "bool (default: False)",
                "timeout": "float (default: 5.0)",
            },
            "demo_url": "http://127.0.0.1:8080/snapshot?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/snapshot?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/snapshot",
                    "body": {"url": "http://example.com", "image_format": "jpeg"},
                },
            ],
        },
        {
            "route": "/docs",
            "methods": ["GET"],
            "description": "API Documentation",
            "demo_url": "http://127.0.0.1:8080/docs",
        },
    ],
}


class HttpController:
    def __init__(self, engine: ChromeEngine):
        self.engine = engine

    async def _get_params(self, request: web.Request) -> Dict[str, Any]:
        """Extract parameters from GET query or POST JSON body."""
        if request.method == "POST":
            try:
                return await request.json()
            except Exception:
                return dict(request.query)
        return dict(request.query)

    async def download(self, request: web.Request) -> web.Response:
        """Handle download request."""
        params = await self._get_params(request)
        try:
            args = DownloadArgs(**params)
            engine_params = args.to_engine_params()
            result = await self.engine.download(**engine_params)
            return web.json_response(Response(code=0, data=result).to_dict())
        except Exception as e:
            logger.error(f"Download error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def preview(self, request: web.Request) -> web.Response:
        """Handle preview request."""
        params = await self._get_params(request)
        try:
            args = PreviewArgs(**params)
            engine_params = args.to_engine_params()
            result = await self.engine.preview(**engine_params)
            return web.Response(body=result, content_type="text/html")
        except Exception as e:
            logger.error(f"Preview error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def snapshot(self, request: web.Request) -> web.Response:
        """Handle snapshot request."""
        params = await self._get_params(request)
        try:
            args = SnapshotArgs(**params)
            engine_params = args.to_engine_params()
            result = await self.engine.screenshot(**engine_params)
            content_type = f"image/{args.image_format}"
            return web.Response(body=result, content_type=content_type)
        except Exception as e:
            logger.error(f"Snapshot error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def docs(self, request: web.Request) -> web.Response:
        """Handle docs documentation request."""
        return web.json_response(Response(code=0, data=API_DOCS).to_dict())


async def create_app(engine: ChromeEngine):
    app = web.Application()
    controller = HttpController(engine)
    app.router.add_route("*", "/download", controller.download)
    app.router.add_route("*", "/preview", controller.preview)
    app.router.add_route("*", "/snapshot", controller.snapshot)
    app.router.add_route("GET", "/docs", controller.docs)
    return app
