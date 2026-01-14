from typing import Any, Dict

from aiohttp import web
from morebuiltins.utils import format_error

from ..logs import logger
from ..pool import ChromeEngine, DownloadDTO, JsDTO, PreviewDTO, ScreenshotDTO
from ..schemas.http import Response
from .doc import API_DOCS


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
            dto = DownloadDTO.from_dict(params)
            result = await self.engine.download(dto=dto)
            return web.json_response(Response(code=0, data=result).to_dict())
        except Exception as e:
            logger.error(f"Download error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def preview(self, request: web.Request) -> web.Response:
        """Handle preview request."""
        params = await self._get_params(request)
        try:
            dto = PreviewDTO.from_dict(params)
            result = await self.engine.preview(dto=dto)
            return web.Response(body=result, content_type="text/html")
        except Exception as e:
            logger.error(f"Preview error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def snapshot(self, request: web.Request) -> web.Response:
        """Handle snapshot request."""
        params = await self._get_params(request)
        try:
            dto = ScreenshotDTO.from_dict(params)
            result = await self.engine.screenshot(dto=dto)
            content_type = f"image/{dto.format}"
            return web.Response(body=result, content_type=content_type)
        except Exception as e:
            logger.error(f"Snapshot error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def js(self, request: web.Request) -> web.Response:
        """Handle js request."""
        params = await self._get_params(request)
        try:
            dto = JsDTO.from_dict(params)
            result = await self.engine.js(dto=dto)
            return web.json_response(Response(code=0, data=result).to_dict())
        except Exception as e:
            logger.error(f"JS error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def docs(self, request: web.Request) -> web.Response:
        """Handle docs documentation request."""
        return web.json_response(Response(code=0, data=API_DOCS).to_dict())
