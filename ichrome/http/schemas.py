"""
API parameter schemas for ichrome HTTP server.

All parameters use underscore naming and human-readable names.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Union

from morebuiltins.utils import Validator


@dataclass
class Response(Validator):
    """Standard API response structure."""

    code: int = 0
    data: Union[None, Dict, str, int, float, bool] = None
    msg: str = ""

    def to_dict(self) -> Dict[str, Union[None, Dict, str, int, float, bool]]:
        """Convert to dictionary, excluding None values where appropriate."""
        result: dict = {"code": self.code}
        if self.data is not None:
            result["data"] = self.data
        if self.msg:
            result["msg"] = self.msg
        return result


@dataclass
class ServerConfig(Validator):
    """Configuration for the HTTP server."""

    host: str = "0.0.0.0"
    port: int = 8080

    def update(self, data: Dict[str, Any]):
        """Update fields from a dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class ChromeConfig(Validator):
    """Configuration for the Chrome engine."""

    workers_amount: int = 1
    max_concurrent_tabs: int = 5
    start_port: int = 9345
    headless: bool = True
    chrome_path: str = ""
    user_data_dir: str = ""
    disable_image: bool = False
    restart_every: int = 8 * 60
    default_cache_size: int = 100 * 1024**2
    window_size: str = "1920,1080"
    extra_config: list = field(default_factory=list)

    def update(self, data: Dict[str, Any]):
        """Update fields from a dictionary."""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine parameters."""
        extra_config = list(self.extra_config)
        if self.default_cache_size:
            extra_config.append(f"--disk-cache-size={self.default_cache_size}")
        if self.window_size:
            extra_config.append(f"--window-size={self.window_size}")
        params: Dict[str, Any] = {
            "workers_amount": self.workers_amount,
            "max_concurrent_tabs": self.max_concurrent_tabs,
            "start_port": self.start_port,
            "headless": self.headless,
            "chrome_path": self.chrome_path or None,
            "user_data_dir": self.user_data_dir or None,
            "disable_image": self.disable_image,
            "restart_every": self.restart_every,
            "extra_config": extra_config,
        }
        return params


@dataclass
class DownloadArgs(Validator):
    """Parameters for downloading page source."""

    url: str
    css_selector: str = ""
    wait_tag: str = ""
    cookies: Dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    timeout: float = 5.0
    incognito_args: Dict[str, Union[None, Dict, str, int, float, bool]] = field(
        default_factory=dict
    )

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine download parameters."""
        return {
            "url": self.url,
            "cssselector": self.css_selector,
            "wait_tag": self.wait_tag,
            "cookies": self.cookies if self.cookies else None,
            "user_agent": self.user_agent,
            "extra_headers": self.extra_headers if self.extra_headers else None,
            "timeout": self.timeout,
            "incognito_args": self.incognito_args if self.incognito_args else None,
        }


@dataclass
class PreviewArgs(Validator):
    """Parameters for previewing page HTML."""

    url: str
    wait_tag: str = ""
    timeout: float = 5.0

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine preview parameters."""
        return {
            "url": self.url,
            "wait_tag": self.wait_tag,
            "timeout": self.timeout,
        }


@dataclass
class SnapshotArgs(Validator):
    """Parameters for taking screenshots."""

    url: str
    css_selector: str = ""
    scale: float = 1.0
    image_format: str = "png"
    quality: int = 100
    from_surface: bool = True
    save_path: str = ""
    timeout: float = 5.0
    capture_beyond_viewport: bool = False

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine screenshot parameters."""
        return {
            "url": self.url,
            "cssselector": self.css_selector,
            "scale": self.scale,
            "format": self.image_format,
            "quality": self.quality,
            "fromSurface": self.from_surface,
            "save_path": self.save_path if self.save_path else None,
            "timeout": self.timeout,
            "captureBeyondViewport": self.capture_beyond_viewport,
            "as_base64": False,  # No longer supports base64
        }


@dataclass
class DoArgs(Validator):
    """Parameters for custom tab callback."""

    tab_callback: str
    data: Any = None
    timeout: float = 5.0
    incognito_args: dict = field(default_factory=dict)

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine do parameters.
        Note: tab_callback needs to be executed from source string.
        """
        ns: Dict[str, Any] = {}
        exec(self.tab_callback, ns)
        callback_func = ns.get("tab_callback") or ns.get("callback")
        if not callback_func:
            raise ValueError(
                "Neither 'callback' nor 'tab_callback' function (async def callback(tab, data, timeout):) found in source code."
            )

        return {
            "data": self.data,
            "tab_callback": callback_func,
            "timeout": self.timeout,
            "incognito_args": self.incognito_args if self.incognito_args else None,
        }


@dataclass
class JsArgs(Validator):
    """Parameters for executing JavaScript."""

    url: str
    js: str
    value_path: str = "result.result"
    wait_tag: str = ""
    timeout: float = 5.0

    def to_engine_params(self) -> Dict[str, Any]:
        """Convert to ChromeEngine js parameters."""
        return {
            "url": self.url,
            "js": self.js,
            "value_path": self.value_path,
            "wait_tag": self.wait_tag,
            "timeout": self.timeout,
        }
