import typing

from ..logs import logger
from ..pool import ChromeEngine

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse, Response
except ImportError as error:
    logger.error(
        'requirements is not all ready, run `pip install ichrome[web]` or `pip install fastapi uvicorn` first.'
    )
    raise error
"""
import uvicorn
from fastapi import FastAPI

from ichrome.routers.fastapi_routes import router

app = FastAPI()
app.include_router(router, prefix='/chrome')

uvicorn.run(app)

# view url with your browser
# http://127.0.0.1:8000/chrome/screenshot?url=http://bing.com
# http://127.0.0.1:8000/chrome/download?url=http://bing.com
"""


class ChromeEventHandler(object):

    @staticmethod
    async def on_startup():
        await chrome_engine.start()

    @staticmethod
    async def on_shutdown():
        await chrome_engine.shutdown()


chrome_engine = ChromeEngine()
router = APIRouter(on_startup=[ChromeEventHandler.on_startup],
                   on_shutdown=[ChromeEventHandler.on_shutdown])


@router.get('/preview')
async def preview(url: str, wait_tag: str = None, timeout: float = None):
    result = await chrome_engine.preview(url,
                                         wait_tag=wait_tag,
                                         timeout=timeout)
    result = result or b''
    status_code = 200 if result else 400
    return Response(content=result, status_code=status_code)


@router.get('/download')
async def download(url: str,
                   cssselector: str = None,
                   wait_tag: str = None,
                   timeout: typing.Union[float, int] = None):
    result = await chrome_engine.download(url,
                                          cssselector=cssselector,
                                          wait_tag=wait_tag,
                                          timeout=timeout)
    status_code = 200 if result else 400
    return JSONResponse(result or {}, status_code)


@router.get('/screenshot')
async def screenshot(url: str,
                     cssselector: str = None,
                     scale=1,
                     format: str = 'png',
                     quality: int = 100,
                     fromSurface: bool = True,
                     timeout=None):
    result = await chrome_engine.screenshot(url,
                                            cssselector=cssselector,
                                            scale=scale,
                                            format=format,
                                            quality=quality,
                                            fromSurface=fromSurface,
                                            timeout=timeout,
                                            as_base64=False)
    result = result or b''
    status_code = 200 if result else 400
    return Response(content=result, status_code=status_code)


@router.get('/do')
async def do(data: dict, tab_callback: str, timeout: float = None):
    result = await chrome_engine.do(data=data,
                                    tab_callback=tab_callback,
                                    timeout=timeout)
    result = result or {}
    status_code = 200 if result else 400
    return JSONResponse(content=result, status_code=status_code)
