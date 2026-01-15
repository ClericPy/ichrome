import json
from base64 import b64encode
from typing import Any, Dict

from aiohttp import web
from morebuiltins.utils import format_error

from ..logs import logger
from ..pool import ChromeEngine, DownloadDTO, JsDTO, ScreenshotDTO
from ..schemas.http_schema import Response
from .doc import API_DOCS, get_html_docs


class HttpController:
    def __init__(self, engine: ChromeEngine, api_prefix: str = "/"):
        self.engine = engine
        self.api_prefix = api_prefix

    async def _get_params(self, request: web.Request) -> Dict[str, Any]:
        """Extract parameters from GET query or POST JSON body."""
        if request.method == "POST":
            try:
                return await request.json()
            except Exception:
                return dict(request.query)
        return dict(request.query)

    def _is_json_request(self, params: Dict[str, Any]) -> bool:
        """Check if the request asks for a JSON response."""
        for key in ("to_json", "as_json"):
            if params.get(key, "false").lower() in {"1", "true", "yes", "on"}:
                return True
        return False

    async def download(self, request: web.Request) -> web.Response:
        """Handle download request."""
        params = await self._get_params(request)
        to_json = self._is_json_request(params)
        try:
            dto = DownloadDTO.from_dict(params)
            result = await self.engine.download(dto=dto)
            if to_json:
                return web.json_response(
                    Response(code=0, data=result.to_dict()).to_dict()
                )
            else:
                encoding = result.encoding or "utf-8"
                return web.Response(
                    body=result.html.encode(encoding),
                    content_type="text/html",
                    charset=encoding,
                )
        except Exception as e:
            logger.error(f"Download error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def snapshot(self, request: web.Request) -> web.Response:
        """Handle snapshot request."""
        params = await self._get_params(request)
        to_json = self._is_json_request(params)
        try:
            dto = ScreenshotDTO.from_dict(params)
            result = await self.engine.screenshot(dto=dto)
            if to_json:
                return web.json_response(
                    Response(
                        code=0, data={"image_bytes": b64encode(result).decode("utf-8")}
                    ).to_dict()
                )
            else:
                content_type = f"image/{dto.format}"
                return web.Response(body=result, content_type=content_type)
        except Exception as e:
            logger.error(f"Snapshot error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def js(self, request: web.Request) -> web.Response:
        """Handle js request."""
        params = await self._get_params(request)
        to_json = self._is_json_request(params)
        try:
            dto = JsDTO.from_dict(params)
            result = await self.engine.js(dto=dto)
            if to_json:
                return web.json_response(Response(code=0, data=result).to_dict())
            else:
                return web.Response(body=json.dumps(result), content_type="text/plain")
        except Exception as e:
            logger.error(f"JS error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def do(self, request: web.Request) -> web.Response:
        """Handle do custom callback request."""
        params = await self._get_params(request)
        try:
            # result is the returned value from callback
            result = await self.engine.do(
                tab_callback=params.get("tab_callback") or params.get("callback"),
                data=params.get("data"),
                timeout=params.get("timeout"),
                incognito_args=params.get("incognito_args"),
            )
            return web.json_response(Response(code=0, data=result).to_dict())
        except Exception as e:
            logger.error(f"Do error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def docs(self, request: web.Request) -> web.Response:
        """Handle docs documentation request."""
        if request.query.get("json"):
            return web.json_response(Response(code=0, data=API_DOCS).to_dict())
        return web.Response(
            text=get_html_docs(api_prefix=self.api_prefix), content_type="text/html"
        )
