# ichrome.http

`ichrome.http` provides an HTTP server based on `aiohttp`, exposing `ChromeEngine` capabilities via RESTful APIs. It allows environments that cannot directly use the Python SDK to control Chrome for crawling, screenshotting, executing JS, and more via simple HTTP requests.

## Getting Started

Start the server from the command line:

```bash
# Default: listens on 127.0.0.1:8080, uses 1 Chrome worker (port 9345)
python -m ichrome.http

# Custom configuration
python -m ichrome.http --host 0.0.0.0 --port 8081 --workers 2 --start-port 9345 --headless 1
```

### Common CLI Arguments

| Argument | Description | Default |
| --- | --- | --- |
| `--host` | HTTP server binding address | 127.0.0.1 |
| `--port` | HTTP server listening port | 8080 |
| `-w`, `--workers` | Number of Chrome worker processes | 1 |
| `--max-concurrent-tabs` | Max concurrent tabs per worker | 5 |
| `-sp`, `--start-port` | Starting port for Chrome debugging | 9345 |
| `--headless` | Enable headless mode (1 for True, 0 for False) | 1 |
| `--chrome-path` | Path to Chrome executable | Auto-discovered |

## API Endpoints

Once started, visit `http://127.0.0.1:8080/docs` for interactive documentation (if defined). Supported endpoints:

### 1. Page Download (`/download`)

Fetch the HTML source of a page.

- **Method**: `GET` or `POST`
- **Key Parameters**:
    - `url`: Target URL (Required)
    - `cssselector`: Extract HTML of specific CSS selector only (Optional)
- **Example**:
    ```bash
    curl "http://127.0.0.1:8080/download?url=https://bing.com"
    ```

### 2. Screenshot (`/screenshot`)

Take a screenshot of a page and return the image binary.

- **Method**: `GET` or `POST`
- **Key Parameters**:
    - `url`: Target URL (Required)
    - `cssselector`: CSS selector of the element to capture (Optional)
    - `format`: Image format `png` or `jpeg` (Default: `png`)
    - `to_json`: Set to `1` to return base64 data in JSON (Optional)
- **Example**:
    ```bash
    curl "http://127.0.0.1:8080/screenshot?url=https://bing.com&cssselector=#sb_form" --output bing.png
    ```

### 3. Execute JavaScript (`/js`)

Execute custom JavaScript within the page.

- **Method**: `GET` or `POST`
- **Key Parameters**:
    - `url`: Target URL (Required)
    - `js`: JavaScript code to execute (Required)
    - `value_path`: Extraction path for the return value (Default: `result.result`)
- **Example**:
    ```bash
    curl "http://127.0.0.1:8080/js?url=https://bing.com&js=document.title"
    ```

### 4. General Task (`/do`)

Allows custom callback logic (requires a Python environment for the script).

## Advanced Configuration (Nested DTO Params)

APIs support nested parameters via dot notation to pass complex DTO configurations:

- `tab_config.xxx`: `TabConfigDTO` params (e.g., width, height)
- `tab_wait.xxx`: `TabWaitDTO` params (e.g., css, js_true, timeout)

**Example (Screenshot after waiting for a specific CSS element)**:
```bash
curl "http://127.0.0.1:8080/screenshot?url=https://bing.com&tab_wait.css=#sb_form"
```

## Important Notes

- The service automatically manages Chrome processes, including a health-check and auto-restart (default: every 8 minutes per worker to prevent memory leaks).
- Use in trusted internal networks or add an authentication middleware for external access.
