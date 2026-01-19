# API documentation metadata
API_DOCS = {
    "description": (
        "ichrome HTTP API via aiohttp.<br><br>"
        "<b>Nested Parameters:</b> Use dots in keys to pass parameters to nested DTOs.<br>"
        "For example, <code>tab_config.width=1280&tab_config.height=720</code> or <code>tab_prepare.ua=ExampleUA</code>.<br>"
        "Supported prefixes for TabConfigDTO: <code>tab_config</code>.<br>"
        "Supported prefixes for TabPrepareDTO: <code>tab_prepare</code>.<br>"
        "Supported prefixes for TabWaitDTO: <code>tab_wait</code>."
    ),
    "response_schema": {
        "code": "int (0 for success, 1 for error)",
        "data": "any (result data on success)",
        "msg": "str (error message on error)",
    },
    "dtos": {
        "TabConfigDTO": {
            "description": "Configuration for creating or attaching to a tab.",
            "parameters": {
                "url": "str (default: 'about:blank')",
                "width": "int (optional, window width)",
                "height": "int (optional, window height)",
                "enableBeginFrameControl": "bool (optional)",
                "newWindow": "bool (optional)",
                "background": "bool (optional)",
                "disposeOnDetach": "bool (default: True)",
                "proxyServer": "str (optional, e.g. 'http://address:port')",
                "proxyBypassList": "str (optional)",
                "originsWithUniversalNetworkAccess": "list[str] (optional)",
            },
        },
        "TabPrepareDTO": {
            "description": "Preparation for a tab before executing commands.",
            "parameters": {
                "ua": "str (optional)",
                "headers": "dict (optional)",
                "cookies": "dict (optional)",
            },
        },
        "TabWaitDTO": {
            "description": "Wait strategy after page load.",
            "parameters": {
                "all_completed": "bool (optional, default: True)",
                "load": "float (optional, wait loading seconds)",
                "css": "str (optional, wait for css selector)",
                "includes": "str (optional, wait for text inclusion within css element)",
                "regex": "str (optional, wait for regex match within css element)",
                "js_true": "str (optional, wait for js code to return true)",
                "sleep": "float (optional, sleep seconds after conditions met)",
                "request_pattern": "str (optional, wait for request wildcard pattern)",
                "response_pattern": "str (optional, wait for response wildcard pattern)",
            },
        },
    },
    "endpoints": [
        {
            "route": "/download",
            "methods": ["GET", "POST"],
            "description": "Download page source or specific element HTML",
            "parameters": {
                "url": "str (required)",
                "cssselector": "str (optional, element to extract)",
                "timeout": "float (default: 5.0)",
                "tab_config": "dict | dotted keys (optional, e.g., tab_config.width=1280)",
                "tab_prepare": "dict | dotted keys (optional, e.g., tab_prepare.ua=UA)",
                "tab_wait": "dict | dotted keys (optional, e.g., tab_wait.css=.main)",
            },
            "demo_url": "http://127.0.0.1:8080/ichrome/download?url=https://httpbin.org/get&tab_prepare.ua=CustomUA&tab_wait.load=2",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=http://example.com",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=https://www.bing.com/images&cssselector=head+title",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/download",
                    "body": {"url": "http://example.com", "timeout": 10},
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=http://example.com&tab_config.width=1280&tab_config.height=720",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/download?url=http://example.com&tab_wait.css=body&tab_wait.includes=Example",
                },
            ],
        },
        {
            "route": "/screenshot",
            "methods": ["GET", "POST"],
            "description": "Take screenshot (returns image bytes directly)",
            "parameters": {
                "url": "str (required)",
                "cssselector": "str (optional)",
                "scale": "float (default: 1.0)",
                "image_format": "str (png/jpeg, default: png)",
                "quality": "int (1-100, default: 100)",
                "from_surface": "bool (default: True)",
                "capture_beyond_viewport": "bool (default: False)",
                "timeout": "float (default: 5.0)",
                "tab_config": "dict | dotted keys (optional, e.g., tab_config.width=1280)",
                "tab_prepare": "dict | dotted keys (optional, e.g., tab_prepare.ua=UA)",
                "tab_wait": "dict | dotted keys (optional, e.g., tab_wait.load=1)",
            },
            "demo_url": "http://127.0.0.1:8080/screenshot?url=https://www.bing.com/images",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/screenshot?url=https://www.bing.com/images",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/screenshot?url=https://www.bing.com/images&image_format=jpeg",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/screenshot?url=https://www.bing.com/images&scale=0.5&quality=50",
                },
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:8080/screenshot",
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
                "timeout": "float (default: 5.0)",
                "tab_config": "dict | dotted keys (optional, e.g., tab_config.width=1280)",
                "tab_wait": "dict | dotted keys (optional, e.g., tab_wait.load=1)",
            },
            "demo_url": "http://127.0.0.1:8080/js?url=https://www.bing.com/images&js=document.title",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/js?url=https://www.bing.com/images&js=document.body.innerText",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/js?url=https://www.bing.com/images&js=window.location.href",
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
                "tab_config": "dict | dotted keys (optional, e.g., tab_config.width=1280)",
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
