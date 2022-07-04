import typing

from ..logs import logger
from ..pool import ChromeEngine

try:
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from fastapi.routing import APIRoute, APIRouter
    from pydantic import BaseModel
except ImportError as error:
    logger.error(
        'requirements are not all ready, run `pip install ichrome[web]` or `pip install fastapi uvicorn` first.'
    )
    raise error
"""
# ======================= server code ===========================

import os

import uvicorn
from fastapi import FastAPI

from ichrome import AsyncTab
from ichrome.routers.fastapi_routes import ChromeAPIRouter

app = FastAPI()
# reset max_msg_size and window size for a large size screenshot
AsyncTab._DEFAULT_WS_KWARGS['max_msg_size'] = 10 * 1024**2
app.include_router(ChromeAPIRouter(headless=True,
                                   extra_config=['--window-size=1920,1080']),
                   prefix='/chrome')

uvicorn.run(app)

# view url with your browser
# http://127.0.0.1:8000/chrome/screenshot?url=http://bing.com
# http://127.0.0.1:8000/chrome/download?url=http://bing.com

# ======================= client code ===========================

from torequests import tPool
from inspect import getsource
req = tPool()


async def tab_callback(self, tab, data, timeout):
    await tab.set_url(data['url'], timeout=timeout)
    return (await tab.querySelector('h1')).text


r = req.post('http://127.0.0.1:8000/chrome/do',
             json={
                 'data': {
                     'url': 'http://httpbin.org/html'
                 },
                 'tab_callback': getsource(tab_callback),
                 'timeout': 10
             })
print(r.text)
# "Herman Melville - Moby-Dick"

# incognito_args demo

async def tab_callback(task, tab, data, timeout):
    await tab.wait_loading(3)
    return await tab.html


print(
    requests.post('http://127.0.0.1:8000/chrome/do',
                  json={
                      'tab_callback': getsource(tab_callback),
                      'timeout': 10,
                      'incognito_args': {
                          'url': 'http://httpbin.org/ip',
                          'proxyServer': 'http://127.0.0.1:1080'
                      }
                  }).text)

"""


class IncognitoArgs(BaseModel):
    url: str = 'about:blank'
    width: int = None
    height: int = None
    enableBeginFrameControl: bool = None
    newWindow: bool = None
    background: bool = None
    disposeOnDetach: bool = True
    proxyServer: str = None
    proxyBypassList: str = None
    originsWithUniversalNetworkAccess: typing.List[str] = None
    flatten: bool = None


class TabOperation(BaseModel):
    tab_callback: str
    data: typing.Any = None
    timeout: float = None
    incognito_args: IncognitoArgs = None


class ChromeAPIRouter(APIRouter):

    def __init__(self,
                 routes=None,
                 redirect_slashes=True,
                 default=None,
                 dependency_overrides_provider=None,
                 route_class=APIRoute,
                 default_response_class=None,
                 on_startup=None,
                 on_shutdown=None,
                 *args,
                 **kwargs):
        super().__init__(
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            dependency_overrides_provider=dependency_overrides_provider,
            route_class=route_class,
            default_response_class=default_response_class,
            on_startup=on_startup,
            on_shutdown=on_shutdown)
        self.setup_chrome_engine(*args, **kwargs)

    def setup_chrome_engine(self, *args, **kwargs):
        self.chrome_engine = ChromeEngine(*args, **kwargs)
        self.get('/preview')(self.preview)
        self.get('/download')(self.download)
        self.get('/screenshot')(self.screenshot)
        self.get('/js')(self.js)
        self.post('/do')(self.do)
        self.add_event_handler('startup', self._chrome_on_startup)
        self.add_event_handler('shutdown', self._chrome_on_shutdown)

    async def _chrome_on_startup(self):
        await self.chrome_engine.start()

    async def _chrome_on_shutdown(self):
        await self.chrome_engine.shutdown()

    async def preview(self,
                      url: str,
                      wait_tag: str = None,
                      timeout: float = None):
        data = await self.chrome_engine.download(url,
                                                 wait_tag=wait_tag,
                                                 timeout=timeout)
        if data:
            return HTMLResponse(data['html'])
        else:
            return Response(content=b'', status_code=400)

    async def download(self,
                       url: str,
                       cssselector: str = None,
                       wait_tag: str = None,
                       timeout: typing.Union[float, int] = None):
        result = await self.chrome_engine.download(url,
                                                   cssselector=cssselector,
                                                   wait_tag=wait_tag,
                                                   timeout=timeout)
        status_code = 200 if result else 400
        return JSONResponse(result or {}, status_code)

    async def screenshot(self,
                         url: str,
                         cssselector: str = None,
                         scale: float = 1,
                         format: str = 'png',
                         quality: int = 100,
                         fromSurface: bool = True,
                         timeout: typing.Union[float, int] = None,
                         captureBeyondViewport: bool = False):
        result = await self.chrome_engine.screenshot(
            url,
            cssselector=cssselector,
            scale=scale,
            format=format,
            quality=quality,
            fromSurface=fromSurface,
            captureBeyondViewport=captureBeyondViewport,
            timeout=timeout,
            as_base64=False)
        result = result or b''
        status_code = 200 if result else 400
        return Response(content=result, status_code=status_code)

    async def do(self, tab_operation: TabOperation):
        if tab_operation.incognito_args is None:
            incognito_args = None
        else:
            incognito_args = dict(tab_operation.incognito_args)
        result = await self.chrome_engine.do(
            data=tab_operation.data,
            tab_callback=tab_operation.tab_callback,
            timeout=tab_operation.timeout,
            incognito_args=incognito_args)
        result = result or {}
        status_code = 200 if result else 400
        return JSONResponse(content=result, status_code=status_code)

    async def js(self,
                 url: str,
                 js: str = None,
                 value_path='result.result',
                 wait_tag: str = None,
                 timeout: typing.Union[float, int] = None):
        result = await self.chrome_engine.js(url,
                                             js=js,
                                             value_path=value_path,
                                             wait_tag=wait_tag,
                                             timeout=timeout)
        status_code = 200 if result else 400
        return JSONResponse(result or {}, status_code)
