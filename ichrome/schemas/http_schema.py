"""
API parameter schemas for ichrome HTTP server.

All parameters use underscore naming and human-readable names.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from morebuiltins.utils import Validator


@dataclass
class Response:
    """Standard API response structure."""

    code: int = 0
    data: Any = None
    msg: str = ""

    def to_dict(self) -> Dict[str, Any]:
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
    api_prefix: str = "/ichrome/"

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
