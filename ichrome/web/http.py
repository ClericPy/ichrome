def start_server():
    import uvicorn
    from fastapi import FastAPI
    import json

    from ..logs import logger
    from ..routers.fastapi_routes import ChromeAPIRouter
    from ..pool import ChromeWorker
    from .config import Config
    app = FastAPI()
    ChromeWorker.RESTART_EVERY = Config['ChromeWorkerArgs']['RESTART_EVERY']
    ChromeWorker.DEFAULT_CACHE_SIZE = Config['ChromeWorkerArgs'][
        'DEFAULT_CACHE_SIZE']
    app.include_router(
        ChromeAPIRouter(**Config['ChromeAPIRouterArgs']),
        prefix=Config['IncludeRouterArgs']['prefix'],
    )
    logger.info(
        f'Starting server with Config: {json.dumps(Config, ensure_ascii=False)}'
    )
    uvicorn.run(app, **Config['UvicornArgs'])
