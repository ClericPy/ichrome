"""
HTTP API server for ichrome, exposing ChromeEngine's functionalities.

Usage:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1

Examples:
    1. Download page source:
        curl "http://127.0.0.1:8080/download?url=http://example.com"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com", "timeout": 10}' http://127.0.0.1:8080/download
    2. Preview page (returns HTML directly):
        curl "http://127.0.0.1:8080/preview?url=http://example.com&wait_tag=body"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com"}' http://127.0.0.1:8080/preview
    3. Take screenshot (returns base64 encoded image):
        curl "http://127.0.0.1:8080/snapshot?url=http://example.com"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com", "scale": 2.0}' http://127.0.0.1:8080/snapshot
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from aiohttp import web
from morebuiltins.utils import Validator, format_error

from ..logs import logger
from ..pool import ChromeEngine


@dataclass
class DownloadArgs(Validator):
    url: str
    cssselector: str = ""
    wait_tag: str = ""
    cookies: Dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 5.0
    incognito_args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewArgs(Validator):
    url: str
    wait_tag: str = ""
    timeout: float = 5.0


@dataclass
class SnapshotArgs(Validator):
    url: str
    cssselector: str = ""
    scale: float = 1.0
    format: str = "png"
    quality: int = 100
    fromSurface: bool = True
    save_path: str = ""
    timeout: float = 5.0
    as_base64: bool = False
    captureBeyondViewport: bool = False


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
            # Validate parameters with dataclass
            args = DownloadArgs(**params)
            result = await self.engine.download(**asdict(args))
            return web.json_response({"code": 0, "data": result})
        except Exception as e:
            logger.error(f"Download error: {format_error(e, filter=None)}")
            return web.json_response({"code": 1, "msg": str(e)}, status=500)

    async def preview(self, request: web.Request) -> web.Response:
        """Handle preview request."""
        params = await self._get_params(request)
        try:
            # Validate parameters with dataclass
            args = PreviewArgs(**params)
            result = await self.engine.preview(**asdict(args))
            return web.Response(body=result, content_type="text/html")
        except Exception as e:
            logger.error(f"Preview error: {format_error(e, filter=None)}")
            return web.json_response({"code": 1, "msg": str(e)}, status=500)

    async def snapshot(self, request: web.Request) -> web.Response:
        """Handle snapshot request."""
        params = await self._get_params(request)
        try:
            # Validate parameters with dataclass
            args = SnapshotArgs(**params)
            result = await self.engine.screenshot(**asdict(args))
            if args.as_base64:
                return web.json_response({"code": 0, "data": result})
            else:
                return web.Response(body=result, content_type="image/png")
        except Exception as e:
            logger.error(f"Snapshot error: {format_error(e, filter=None)}")
            return web.json_response({"code": 1, "msg": str(e)}, status=500)


async def create_app(engine: ChromeEngine):
    app = web.Application()
    controller = HttpController(engine)
    app.router.add_route("*", "/download", controller.download)
    app.router.add_route("*", "/preview", controller.preview)
    app.router.add_route("*", "/snapshot", controller.snapshot)
    return app
