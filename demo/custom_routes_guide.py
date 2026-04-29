"""
Custom routes example for ichrome HTTP server.

Subclass HttpController to add your own endpoints,
then set HttpServer.controller_class to your subclass.

Usage:
    python demo/custom_routes_guide.py
"""

import asyncio
from urllib.parse import quote_plus

from aiohttp import web

from ichrome.async_utils import AsyncTab
from ichrome.http import HttpController, HttpServer
from ichrome.schemas.http_schema import ChromeConfig, ServerConfig


class MyController(HttpController):
    def __init__(self, engine, api_prefix="/"):
        super().__init__(engine, api_prefix=api_prefix)
        self.routers += [
            ("GET", "/health", self.health),
            ("*", f"/{self.search.__name__}", self.search),
        ]

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def search(self, request: web.Request) -> web.Response:
        """search with bing return the titles"""
        kw = request.query.get("q", "")
        if not kw:
            return web.json_response(
                {"error": "missing query parameter 'q'"}, status=400
            )
        url = "https://www.bing.com/search?q=%s" % quote_plus(kw)

        async def _get_titles(tab: AsyncTab, data, task):
            await tab.set_url(url)
            for _ in range(5):
                await asyncio.sleep(1)
                tags = await tab.querySelectorAll("#b_results >li >h2 > a")
                if tags and isinstance(tags, list):
                    return [i.text for i in tags]
            return []

        result = await self.engine.do(tab_callback=_get_titles, data=None)
        return web.json_response({"url": url, "titles": result})


async def main():
    chrome_config = ChromeConfig(headless=True, workers_amount=1)
    server_config = ServerConfig(host="127.0.0.1", port=8080, api_prefix="/ichrome/demo/")
    server = HttpServer(chrome_config, server_config)
    server.controller_class = MyController
    print(
        "visit http://127.0.0.1:8080/ichrome/demo/search?q=nba to see the demo",
        flush=True,
    )
    async with server:
        await server.run_server()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
