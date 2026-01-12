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
    3. Take screenshot (returns base64 encoded image):
        curl "http://127.0.0.1:8080/snapshot?url=http://example.com"
        curl -X POST -H "Content-Type: application/json" -d '{"url": "http://example.com", "scale": 2.0}' http://127.0.0.1:8080/snapshot
        curl "http://127.0.0.1:8080/snapshot?url=http://example.com&as_base64=0" --output screenshot.png
"""

from .core import (
    DownloadArgs,
    PreviewArgs,
    SnapshotArgs,
    HttpController,
    create_app,
)

__all__ = [
    "DownloadArgs",
    "PreviewArgs",
    "SnapshotArgs",
    "HttpController",
    "create_app",
]
