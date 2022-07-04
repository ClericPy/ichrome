Config = {
    'IncludeRouterArgs': {
        'prefix': '/chrome',
    },
    'UvicornArgs': {
        'host': '127.0.0.1',
        'port': 8080,
    },
    'ChromeAPIRouterArgs': {
        'start_port': 9345,
        'workers_amount': 1,
        'max_concurrent_tabs': 5,
        'headless': True,
        'extra_config': ['--window-size=800,600'],
    },
    'ChromeWorkerArgs': {
        'RESTART_EVERY': 8 * 60,
        'DEFAULT_CACHE_SIZE': 100 * 1024**2,
    },
}
