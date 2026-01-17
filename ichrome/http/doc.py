# API documentation metadata
API_DOCS = {
    "description": (
        "ichrome HTTP API via aiohttp.<br><br>"
        "<b>Nested Parameters:</b> Use dots in keys to pass parameters to nested DTOs.<br>"
        "For example, <code>tab_config.width=1280&tab_config.height=720</code> or <code>tab_prepare.ua=ExampleUA</code>.<br>"
        "Supported prefixes for TabConfigDTO: <code>tab_config</code>.<br>"
        "Supported prefixes for TabPrepareDTO: <code>tab_prepare</code>."
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
            },
            "demo_url": "http://127.0.0.1:8080/ichrome/download?url=https://httpbin.org/get&tab_prepare.ua=CustomUA",
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
            ],
        },
        {
            "route": "/snapshot",
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
            },
            "demo_url": "http://127.0.0.1:8080/snapshot?url=https://www.bing.com/images",
            "examples": [
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/snapshot?url=https://www.bing.com/images",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/snapshot?url=https://www.bing.com/images&image_format=jpeg",
                },
                {
                    "method": "GET",
                    "url": "http://127.0.0.1:8080/snapshot?url=https://www.bing.com/images&scale=0.5&quality=50",
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
                "timeout": "float (default: 5.0)",
                "tab_config": "dict | dotted keys (optional, e.g., tab_config.width=1280)",
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


def get_html_docs(api_prefix="/"):
    """Generate HTML documentation from API_DOCS."""
    import json

    prefix = "/" + api_prefix.strip("/")
    if prefix == "/":
        prefix = ""

    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ichrome API Documentation</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f4f7f6;
        }}
        h1, h2, h3 {{
            color: #2c3e50;
        }}
        .endpoint {{
            background: #fff;
            padding: 20px;
            margin-bottom: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .method {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            margin-right: 10px;
            font-size: 0.9em;
        }}
        .method-GET {{ background-color: #61affe; color: #fff; }}
        .method-POST {{ background-color: #49cc90; color: #fff; }}
        .route {{
            font-family: monospace;
            font-size: 1.2em;
            color: #d63384;
        }}
        .description {{
            margin: 10px 0;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            text-align: left;
            padding: 10px;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background-color: #fcfcfc;
            color: #555;
        }}
        pre {{
            background: #272822;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        a {{
            color: #007bff;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .demo-link {{
            display: block;
            margin-top: 10px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>ichrome API Documentation</h1>
    <p>{description}</p>
    
    <h2>Response Schema</h2>
    <div class="endpoint">
        <table>
            <thead>
                <tr>
                    <th>Field</th>
                    <th>Type / Description</th>
                </tr>
            </thead>
            <tbody>
                {response_schema_rows}
            </tbody>
        </table>
    </div>

    <h2>Endpoints (Prefix: <code>{prefix_display}</code>)</h2>
    {endpoints_html}

    <h2>Data Transfer Objects (DTOs)</h2>
    {dtos_html}

</body>
</html>
    """

    description = API_DOCS["description"]
    response_schema_rows = "".join(
        f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
        for k, v in API_DOCS["response_schema"].items()
    )

    dtos_html = ""
    for dto_name, dto_info in API_DOCS.get("dtos", {}).items():
        dto_params_rows = "".join(
            f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
            for k, v in dto_info["parameters"].items()
        )
        dtos_html += f"""
        <div class="endpoint">
            <h3>{dto_name}</h3>
            <div class="description">{dto_info["description"]}</div>
            <table>
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Type / Description</th>
                    </tr>
                </thead>
                <tbody>
                    {dto_params_rows}
                </tbody>
            </table>
        </div>
        """

    endpoints_html = ""
    for ep in API_DOCS["endpoints"]:
        methods_html = "".join(
            f'<span class="method method-{m}">{m}</span>' for m in ep["methods"]
        )
        params_rows = ""
        if "parameters" in ep:
            params_rows = """
            <h3>Parameters</h3>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type / Description</th>
                    </tr>
                </thead>
                <tbody>
            """
            params_rows += "".join(
                f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
                for k, v in ep["parameters"].items()
            )
            params_rows += "</tbody></table>"

        examples_html = ""
        if "examples" in ep:
            examples_html = "<h3>Examples</h3>"
            for ex in ep["examples"]:
                if ex.get("method") == "GET" and "url" in ex:
                    # Create a clickable link for GET examples
                    original_url = ex["url"]
                    # Extract the query part and rebuild with the current prefix
                    # Assuming format: http://127.0.0.1:8080/route?query
                    try:
                        path_parts = original_url.split(ep["route"], 1)
                        query = path_parts[1] if len(path_parts) > 1 else ""
                        clickable_url = prefix + ep["route"] + query
                    except Exception:
                        clickable_url = original_url
                    
                    examples_html += f"""
                    <div style="margin-bottom: 10px;">
                        <span class="method method-GET">GET</span>
                        <a href="{clickable_url}" target="_blank" class="json-link">{clickable_url}</a>
                    </div>
                    """
                else:
                    ex_json = json.dumps(ex, indent=4)
                    examples_html += f"<pre><code>{ex_json}</code></pre>"

        demo_url_html = ""
        full_route = prefix + ep["route"]
        demo_url_html += f'<div class="demo-link">Endpoint: <span class="route">{full_route}</span></div>'
        
        if "demo_url" in ep:
            d_url = ep["demo_url"]
            try:
                # Rebuild clickable URL using current prefix
                query = d_url.split(ep["route"], 1)[1]
                clickable = prefix + ep["route"] + query
                demo_url_html += f'<div class="demo-link">Quick Demo: <a href="{clickable}" target="_blank">{clickable}</a></div>'
                
                # Add to_json=1 version
                sep = "&" if "?" in clickable else "?"
                json_clickable = f"{clickable}{sep}to_json=1"
                demo_url_html += f'<div class="demo-link">Quick Demo (JSON): <a href="{json_clickable}" target="_blank">{json_clickable}</a></div>'
            except Exception:
                pass
        
        # Add a "Try it out" link if it's a documentation-friendly GET route
        if ep["route"] == "/docs":
             demo_url_html += f'<div class="demo-link"><a href="{full_route}?to_json=1" target="_blank">View JSON API metadata</a></div>'

        endpoints_html += f"""
        <div class="endpoint">
            <div>{methods_html} <span class="route">{full_route}</span></div>
            <div class="description">{ep["description"]}</div>
            {params_rows}
            {examples_html}
            {demo_url_html}
        </div>
        """

    return html_template.format(
        description=description,
        response_schema_rows=response_schema_rows,
        endpoints_html=endpoints_html,
        dtos_html=dtos_html,
        prefix_display=prefix or "/",
    )
