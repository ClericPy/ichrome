import json
from base64 import b64encode
from typing import Any, Dict, Tuple

from aiohttp import web
from morebuiltins.utils import format_error

from ..logs import logger
from ..pool import ChromeEngine, DownloadDTO, JsDTO, ScreenshotDTO, TabConfigDTO
from ..schemas.engine_schema import DTOBase
from ..schemas.http_schema import Response
from .doc import API_DOCS, get_html_docs


class HttpController:
    # config -> TabConfigDTO
    key_map = {"tab_config": TabConfigDTO}

    def __init__(self, engine: ChromeEngine, api_prefix: str = "/"):
        self.engine = engine
        self.api_prefix = api_prefix

    async def _get_params(
        self, request: web.Request
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
        """Extract parameters from GET query or POST JSON body."""
        if request.method == "POST":
            try:
                data = await request.json()
            except Exception:
                data = dict(request.query)
        else:
            data = dict(request.query)
        to_json = self._is_json_request(data)
        dto_params = {}
        other_dtos: Dict[str, DTOBase] = {}
        nested_cache: Dict[str, Dict[str, Any]] = {}

        for k, v in data.items():
            if "." in k:
                k1, k2 = k.split(".", 1)
                if k1 in self.key_map:
                    if k1 in nested_cache:
                        nested_cache[k1][k2] = v
                    else:
                        nested_cache[k1] = {k2: v}
                    continue
            elif k in self.key_map:
                if isinstance(v, dict):
                    nested_cache[k] = v
                else:
                    raise ValueError(
                        f"Expected dict for nested DTO '{k}', got {type(v)}"
                    )
                continue
            dto_params[k] = v
        for nk, nv in nested_cache.items():
            dto_cls = self.key_map.get(nk)
            if dto_cls:
                other_dtos[nk] = dto_cls.from_dict(nv)
        return to_json, dto_params, other_dtos

    def _is_json_request(self, params: Dict[str, Any]) -> bool:
        """Check if the request asks for a JSON response."""
        if params.pop("to_json", "false").lower() in {"1", "true", "yes", "on"}:
            return True
        return False

    async def download(self, request: web.Request) -> web.Response:
        """Handle download request."""
        to_json, dto_params, other_dtos = await self._get_params(request)
        try:
            dto = DownloadDTO.from_dict(dto_params)
            result = await self.engine.download(dto=dto, **other_dtos)
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
        to_json, dto_params, other_dtos = await self._get_params(request)
        try:
            dto = ScreenshotDTO.from_dict(dto_params)
            result = await self.engine.screenshot(dto=dto, **other_dtos)
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
        to_json, dto_params, other_dtos = await self._get_params(request)
        try:
            dto = JsDTO.from_dict(dto_params)
            result = await self.engine.js(dto=dto, **other_dtos)
            if to_json:
                return web.json_response(Response(code=0, data=result).to_dict())
            else:
                return web.Response(body=json.dumps(result), content_type="text/plain")
        except Exception as e:
            logger.error(f"JS error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def do(self, request: web.Request) -> web.Response:
        """Handle do custom callback request."""
        _, dto_params, other_dtos = await self._get_params(request)
        try:
            # result is the returned value from callback
            result = await self.engine.do(
                tab_callback=dto_params.get("tab_callback")
                or dto_params.get("callback"),
                data=dto_params.get("data"),
                timeout=dto_params.get("timeout"),
                **other_dtos,
            )
            return web.json_response(Response(code=0, data=result).to_dict())
        except Exception as e:
            logger.error(f"Do error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=str(e)).to_dict(), status=500)

    async def docs(self, request: web.Request) -> web.Response:
        """Handle docs documentation request."""
        to_json, *_ = await self._get_params(request)
        if to_json:
            return web.json_response(Response(code=0, data=API_DOCS).to_dict())
        return web.Response(
            text=get_html_docs(api_prefix=self.api_prefix), content_type="text/html"
        )
