"""
HTTP API server for ichrome, exposing ChromeEngine's functionalities.

This module provides an HTTP server that wraps ichrome.pool's download, preview,
and screenshot functionalities, allowing them to be accessed via REST API endpoints.

Usage:
    python -m ichrome.http --host 0.0.0.0 --port 8080 --workers 1

Examples:
    1. Download page source:
        curl "http://127.0.0.1:8080/download?url=http://example.com"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com", "timeout": 10}' http://127.0.0.1:8080/download
    2. Preview page (returns HTML directly):
        curl "http://127.0.0.1:8080/preview?url=http://example.com&wait_tag=body"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com"}' http://127.0.0.1:8080/preview
    3. Take screenshot (returns image bytes):
        curl "http://127.0.0.1:8080/snapshot?url=http://example.com" --output screenshot.png
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com", "scale": 2.0}' http://127.0.0.1:8080/snapshot --output screenshot.png
    4. View API documentation:
        curl "http://127.0.0.1:8080/docs"
"""

from .core import (
    HttpController,
    create_app,
)
from .schemas import (
    DownloadArgs,
    PreviewArgs,
    SnapshotArgs,
)

__all__ = [
    "DownloadArgs",
    "PreviewArgs",
    "SnapshotArgs",
    "HttpController",
    "create_app",
]
