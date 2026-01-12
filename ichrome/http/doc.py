# API documentation metadata
API_DOCS = {
    "description": "ichrome HTTP API via aiohttp",
    "response_schema": {
        "code": "int (0 for success, 1 for error)",
        "data": "any (result data on success)",
        "msg": "str (error message on error)",
    },
    "endpoints": [
        {
            "route": "/download",
            "methods": ["GET", "POST"],
            "description": "Download page source or specific element HTML",
            "parameters": {
                "url": "str (required)",
                "css_selector": "str (optional, element to extract)",
                "wait_tag": "str (optional, wait before returning)",
                "timeout": "float (default: 5.0)",
                "cookies": "dict (optional)",
                "user_agent": "str (optional)",
                "extra_headers": "dict (optional)",
                "incognito_args": "dict (optional)",
            },
            "demo_url": "http://127.0.0.1:8080/download?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/download",
                    "body": {"url": "http://example.com", "timeout": 10},
                },
            ],
        },
        {
            "route": "/preview",
            "methods": ["GET", "POST"],
            "description": "Preview page HTML (returns text/html directly)",
            "parameters": {
                "url": "str (required)",
                "wait_tag": "str (optional)",
                "timeout": "float (default: 5.0)",
            },
            "demo_url": "http://127.0.0.1:8080/preview?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/preview?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/preview",
                    "body": {"url": "http://example.com"},
                },
            ],
        },
        {
            "route": "/snapshot",
            "methods": ["GET", "POST"],
            "description": "Take screenshot (returns image bytes directly)",
            "parameters": {
                "url": "str (required)",
                "css_selector": "str (optional)",
                "scale": "float (default: 1.0)",
                "image_format": "str (png/jpeg, default: png)",
                "quality": "int (1-100, default: 100)",
                "from_surface": "bool (default: True)",
                "capture_beyond_viewport": "bool (default: False)",
                "timeout": "float (default: 5.0)",
            },
            "demo_url": "http://127.0.0.1:8080/snapshot?url=http://example.com",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/snapshot?url=http://example.com",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/snapshot",
                    "body": {"url": "http://example.com", "image_format": "jpeg"},
                },
            ],
        },
        {
            "route": "/js",
            "methods": ["GET", "POST"],
            "description": "Execute JavaScript on page",
            "parameters": {
                "url": "str (required)",
                "js": "str (required, javascript code)",
                "value_path": "str (optional, result path)",
                "wait_tag": "str (optional)",
                "timeout": "float (default: 5.0)",
            },
            "demo_url": "http://127.0.0.1:8080/js?url=http://example.com&js=document.body.innerText",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/js?url=http://example.com&js=document.body.innerText",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/js",
                    "body": {
                        "url": "http://example.com",
                        "js": "document.body.innerHTML",
                        "value_path": "result.result.value",
                    },
                },
            ],
        },
        {
            "route": "/do",
            "methods": ["POST"],
            "description": "Execute custom callback function on tab (supports 'callback' or 'tab_callback' name)",
            "parameters": {
                "tab_callback": "str (required, python source. Define 'async def callback(tab, data, timeout):' or 'async def tab_callback(tab, data, timeout):')",
                "data": "any (optional, passed to callback)",
                "timeout": "float (default: 5.0)",
                "incognito_args": "dict (optional)",
            },
            "demo_url": "http://127.0.0.1:8080/do",
            "examples": [
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/do",
                    "body": {
                        "tab_callback": "async def callback(tab, data, timeout): await tab.goto(data['url']); return await tab.title",
                        "data": {"url": "http://example.com"},
                    },
                }
            ],
        },
        {
            "route": "/docs",
            "methods": ["GET"],
            "description": "API Documentation",
            "demo_url": "http://127.0.0.1:8080/docs",
        },
    ],
}
