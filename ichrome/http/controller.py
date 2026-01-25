import asyncio
import json
from ast import literal_eval
from base64 import b64encode
from typing import Any, Dict, Optional, Tuple, Type

from aiohttp import web
from morebuiltins.utils import format_error

from ..logs import logger
from ..pool import (
    ChromeEngine,
    DownloadDTO,
    JsDTO,
    ScreenshotDTO,
    TabConfigDTO,
    TabPrepareDTO,
    TabWaitDTO,
)
from ..schemas.engine_schema import DTOBase
from ..schemas.http_schema import Response
from .doc import API_DOCS, get_html_docs


class HttpController:
    # config -> TabConfigDTO
    key_map: Dict[str, Type[DTOBase]] = {
        "tab_config": TabConfigDTO,
        "tab_prepare": TabPrepareDTO,
        "tab_wait": TabWaitDTO,
    }

    def __init__(self, engine: ChromeEngine, api_prefix: str = "/"):
        self.engine = engine
        self.api_prefix = api_prefix

    async def _get_params(
        self, request: web.Request
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], Optional[float]]:
        """Extract parameters from GET query or POST JSON body."""
        if request.method == "POST":
            if request.content_type == "application/json":
                try:
                    data = await request.json()
                except Exception:
                    data = dict(request.query)
            elif request.content_type == "application/x-www-form-urlencoded":
                data = dict(await request.post())
            else:
                data = dict(request.query)
        else:
            data = dict(request.query)
        to_json = self._is_json_request(data)
        dto_params = {}
        other_dtos: Dict[str, DTOBase] = {}
        nested_cache: Dict[str, Dict[str, Any]] = {}
        timeout = None
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
            elif k == "timeout":
                try:
                    timeout = float(v)
                except ValueError:
                    pass
            dto_params[k] = v
        for nk, nv in nested_cache.items():
            dto_cls = self.key_map.get(nk)
            if dto_cls:
                other_dtos[nk] = dto_cls.from_dict(nv)
        return to_json, dto_params, other_dtos, timeout

    def _is_json_request(self, params: Dict[str, Any]) -> bool:
        """Check if the request asks for a JSON response."""
        if params.pop("to_json", "false").lower() in {"1", "true", "yes", "on"}:
            return True
        return False

    async def download(self, request: web.Request) -> web.Response:
        """Handle download request."""
        to_json, dto_params, other_dtos, timeout = await self._get_params(request)
        try:
            dto = DownloadDTO.from_dict(dto_params)
            result = await self.engine.download(dto=dto, timeout=timeout, **other_dtos)
            if not result:
                raise ValueError("Download returned no result")
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
            return web.json_response(Response(code=1, msg=repr(e)).to_dict(), status=500)

    async def screenshot(self, request: web.Request) -> web.Response:
        """Handle screenshot request."""
        to_json, dto_params, other_dtos, timeout = await self._get_params(request)
        try:
            dto = ScreenshotDTO.from_dict(dto_params)
            result = await self.engine.screenshot(
                dto=dto, timeout=timeout, **other_dtos
            )
            if not result:
                raise ValueError("Screenshot returned no result")
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
            logger.error(f"Screenshot error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=repr(e)).to_dict(), status=500)

    async def js(self, request: web.Request) -> web.Response:
        """Handle js request."""
        to_json, dto_params, other_dtos, timeout = await self._get_params(request)
        try:
            dto = JsDTO.from_dict(dto_params)
            result = await self.engine.js(dto=dto, timeout=timeout, **other_dtos)
            if to_json:
                return web.json_response(Response(code=0, data=result).to_dict())
            else:
                return web.Response(
                    body=json.dumps(result, ensure_ascii=False),
                    content_type="text/plain",
                    charset="utf-8",
                )
        except Exception as e:
            logger.error(f"JS error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=repr(e)).to_dict(), status=500)

    def _parse_callback(self, code: Any) -> Any:
        if not isinstance(code, str):
            return code
        if "def " in code:
            loc: Dict[str, Any] = {}
            exec(code, globals(), loc)
            for name in ("tab_callback", "callback"):
                func = loc.get(name)
                if callable(func) and asyncio.iscoroutinefunction(func):
                    return func
        raise ValueError(
            "Invalid callback code, must define 'tab_callback' or 'callback' like: `async def callback(tab, data, task): ...`"
        )

    async def do(self, request: web.Request) -> web.Response:
        """Handle do custom callback request."""
        _, dto_params, other_dtos, timeout = await self._get_params(request)
        try:
            # result is the returned value from callback
            code = dto_params.get("tab_callback") or dto_params.get("callback")
            data = dto_params.get("data")
            if isinstance(data, str):
                for method in (json.loads, literal_eval):
                    try:
                        data = method(data)
                        break
                    except ValueError:
                        pass
            result = await self.engine.do(
                tab_callback=self._parse_callback(code),
                data=data,
                timeout=timeout,
                **other_dtos,
            )
            # check isinstance of web.Response to return directly
            if isinstance(result, web.Response):
                return result
            else:
                resp = Response(code=0, data=None)
                if isinstance(result, bytes):
                    result = {"data_base64": b64encode(result).decode("utf-8")}
                elif isinstance(result, str):
                    pass
                elif isinstance(result, (int, float, dict, list, type(None))):
                    try:
                        result = json.loads(json.dumps(result, default=repr))
                    except Exception:
                        result = repr(result)
                else:
                    result = repr(result)
                resp.data = result
                return web.json_response(resp.to_dict())
        except Exception as e:
            logger.error(f"Do error: {format_error(e, filter=None)}")
            return web.json_response(Response(code=1, msg=repr(e)).to_dict(), status=500)

    async def docs(self, request: web.Request) -> web.Response:
        """Handle docs documentation request."""
        to_json, *_ = await self._get_params(request)
        if to_json:
            return web.json_response(Response(code=0, data=API_DOCS).to_dict())
        return web.Response(
            text=get_html_docs(api_prefix=self.api_prefix), content_type="text/html"
        )
