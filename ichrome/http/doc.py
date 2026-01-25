from .doc_meta import API_DOCS


def get_html_docs(api_prefix="/"):
    """Generate HTML documentation from API_DOCS."""
    import json
    import urllib.parse

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
        .feature-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75em;
            margin-left: 8px;
            vertical-align: middle;
        }}
        .featured {{
            border: 2px solid #ffc107;
            background: linear-gradient(135deg, #fff9e6 0%, #ffffff 100%);
            position: relative;
        }}
        .featured::before {{
            content: "⭐";
            position: absolute;
            top: -10px;
            right: -10px;
            font-size: 1.5em;
            background: #ffc107;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }}
        .badge-download {{
            background-color: #28a745;
            color: #fff;
        }}
        .badge-screenshot {{
            background-color: #17a2b8;
            color: #fff;
        }}
        .badge-js {{
            background-color: #fd7e14;
            color: #fff;
        }}
        .badge-html {{
            background-color: #6f42c1;
            color: #fff;
        }}
        .badge-pdf {{
            background-color: #dc3545;
            color: #fff;
        }}
        .try-it-out {{
            margin-top: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }}
        .form-group {{
            margin-bottom: 10px;
        }}
        .form-group label {{
            display: inline-block;
            width: 140px;
            font-weight: bold;
            font-size: 0.9em;
        }}
        .form-group input[type="text"] {{
            width: calc(100% - 160px);
            padding: 6px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-family: monospace;
        }}
        .form-group textarea {{
            width: calc(100% - 160px);
            padding: 6px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-family: monospace;
            vertical-align: top;
            min-height: 80px;
            resize: vertical;
        }}
        .try-it-out h4 {{
            margin-top: 0;
            margin-bottom: 15px;
            color: #495057;
            border-bottom: 1px solid #eee;
            padding-bottom: 5px;
        }}
        .try-it-out button {{
            background-color: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin-right: 5px;
        }}
        .try-it-out button:hover {{
            background-color: #0056b3;
        }}
        .try-it-out .method-POST-btn {{
            background-color: #49cc90;
        }}
        .try-it-out .method-POST-btn:hover {{
            background-color: #3cb371;
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

        # Determine if this endpoint should be featured
        featured_class = ""
        feature_badge = ""
        route_lower = ep["route"].lower()

        if "download" in route_lower or "save" in route_lower:
            featured_class = "featured"
            feature_badge = (
                '<span class="feature-badge badge-download">📥 Download</span>'
            )
        elif "screenshot" in route_lower:
            featured_class = "featured"
            feature_badge = (
                '<span class="feature-badge badge-screenshot">📷 Screenshot</span>'
            )
        elif (
            "js" in route_lower or "javascript" in route_lower or "eval" in route_lower
        ):
            featured_class = "featured"
            feature_badge = '<span class="feature-badge badge-js">⚡ JS</span>'
        elif "html" in route_lower:
            featured_class = "featured"
            feature_badge = '<span class="feature-badge badge-html">🌐 HTML</span>'
        elif "pdf" in route_lower:
            featured_class = "featured"
            feature_badge = '<span class="feature-badge badge-pdf">📄 PDF</span>'

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

        # Try it out form
        form_inputs = []
        if "parameters" in ep:
            for k, v in ep["parameters"].items():
                if k in ("tab_config", "tab_prepare", "tab_wait"):
                    continue
                # Use value from examples if possible
                default_val = ""
                if "examples" in ep:
                    for ex in ep["examples"]:
                        if k in ex.get("body", {}):
                            default_val = ex["body"][k]
                            break
                        # Check query params in GET examples
                        if (
                            ex.get("method") == "GET"
                            and "url" in ex
                            and f"{k}=" in ex["url"]
                        ):
                            try:
                                parsed = urllib.parse.urlparse(ex["url"])
                                qs = urllib.parse.parse_qs(parsed.query)
                                if k in qs:
                                    default_val = qs[k][0]
                                    break
                            except Exception:
                                continue

                placeholder = v.split("(")[0].strip()
                if k in ("tab_callback", "js") or "callback" in k:
                    input_html = f'<textarea name="{k}" placeholder="{placeholder}">{default_val}</textarea>'
                else:
                    input_html = f'<input type="text" name="{k}" value="{default_val}" placeholder="{placeholder}">'

                form_inputs.append(
                    f"""
                <div class="form-group">
                    <label>{k}:</label>
                    {input_html}
                </div>
                """
                )

        # Add to_json checkbox
        form_inputs.append(
            """
                <div class="form-group">
                    <label>to_json:</label>
                    <input type="checkbox" name="to_json" value="1"> <span>(JSON response)</span>
                </div>
        """
        )

        buttons_html = "".join(
            [
                f'<button type="submit" class="method-{m}-btn" onclick="this.form.method=\'{m}\'">{m}</button> '
                for m in ep["methods"]
            ]
        )

        try_it_out_html = f"""
        <div class="try-it-out">
            <h4>⚡ Try it out</h4>
            <form action="{full_route}" method="GET" target="_blank">
                {''.join(form_inputs)}
                <div class="form-group" style="margin-top: 15px;">
                    <label></label>
                    {buttons_html}
                </div>
            </form>
        </div>
        """

        endpoints_html += f"""
        <div class="endpoint {featured_class}">
            <div>{methods_html} <span class="route">{full_route}</span>{feature_badge}</div>
            <div class="description">{ep["description"]}</div>
            {params_rows}
            {examples_html}
            {demo_url_html}
            {try_it_out_html}
        </div>
        """

    return html_template.format(
        description=description,
        response_schema_rows=response_schema_rows,
        endpoints_html=endpoints_html,
        dtos_html=dtos_html,
        prefix_display=prefix or "/",
    )
