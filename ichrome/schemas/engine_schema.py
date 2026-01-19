import json
import typing
from ast import literal_eval
from dataclasses import dataclass, field, fields


@dataclass
class DTOBase:
    """Only python basic types are supported: str, int, float, bool, dict, list."""

    @staticmethod
    def _ensure_bool_string(value: str) -> bool:
        return value.lower() in {"1", "true", "yes", "on"}

    string_callbacks = {
        int: int,
        float: float,
        bool: _ensure_bool_string,
        dict: json.loads,
        list: json.loads,
    }

    @staticmethod
    def try_parse_string(value, expected_type) -> typing.Any:
        """Try to parse string value to expected type."""
        if expected_type is int:
            return int(value)
        elif expected_type is float:
            return float(value)
        elif expected_type is bool:
            return DTOBase._ensure_bool_string(value)
        elif expected_type is dict or expected_type is list:
            try:
                # first try json.loads
                return json.loads(value)
            except json.JSONDecodeError:
                # fallback to literal_eval
                return literal_eval(value)
        return value

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> typing.Self:
        field_types = {f.name: f.type for f in fields(cls)}
        init_data = {}
        for key, value in data.items():
            if key in field_types:
                field_type = field_types[key]
                expected_types = typing.get_args(field_type) or (field_type,)
                for expected_type in expected_types:
                    # convert str to expected type
                    if type(value) is str and expected_type in cls.string_callbacks:
                        try:
                            value = cls.try_parse_string(value, expected_type)
                            break
                        except Exception:
                            continue
                init_data[key] = value
        return cls(**init_data)


@dataclass
class ScreenshotDTO(DTOBase):
    """Parameters for taking screenshots."""

    url: str
    cssselector: typing.Optional[str] = None
    scale: float = 1.0
    format: str = "png"
    quality: int = 100
    fromSurface: bool = True
    captureBeyondViewport: bool = False


@dataclass
class DownloadDTO(DTOBase):
    """Parameters for downloading page source."""

    url: str
    cssselector: str = ""


@dataclass
class DownloadResult:
    """Result of a download operation."""

    url: str = ""
    title: str = ""
    encoding: str = ""
    current_url: str = ""
    html: str = ""
    tags: typing.List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "url": self.url,
            "title": self.title,
            "encoding": self.encoding,
            "current_url": self.current_url,
            "html": self.html,
            "tags": self.tags,
        }


@dataclass
class JsDTO(DTOBase):
    """Parameters for executing JavaScript."""

    url: str
    js: str
    value_path: str = "result.result"


@dataclass
class TabConfigDTO(DTOBase):
    url: str = "about:blank"
    width: typing.Optional[int] = None
    height: typing.Optional[int] = None
    enableBeginFrameControl: typing.Optional[bool] = None
    newWindow: typing.Optional[bool] = None
    background: typing.Optional[bool] = None
    disposeOnDetach: bool = True
    proxyServer: typing.Optional[str] = None
    proxyBypassList: typing.Optional[str] = None
    originsWithUniversalNetworkAccess: typing.Optional[typing.List[str]] = None


@dataclass
class TabPrepareDTO(DTOBase):
    cookies: typing.Optional[typing.Dict[str, str]] = None
    ua: str = ""
    headers: typing.Optional[typing.Dict[str, str]] = None
    # split by |, for multiple patterns. support wildcard *: *.example.com/*|*.bing.com/* => ["*.example.com/*", "*.bing.com/*]
    block_urls: typing.Optional[str] = None
    add_js_onload: typing.Optional[str] = None


@dataclass
class TabWaitDTO(DTOBase):
    strategy: str = "all"  # all / any
    loading: typing.Optional[float] = None
    # CSS selector that should appear in the page; could be used with include/exclude/wait_regex together
    css: typing.Optional[str] = None
    # text
    include: typing.Optional[str] = None
    # text
    exclude: typing.Optional[str] = None
    # regex pattern
    regex: typing.Optional[str] = None
    # js_code that returns true
    js_true: typing.Optional[str] = None
    # sleep(seconds) after all conditions met
    sleep: typing.Optional[float] = None
    # wildcard pattern, e.g. *.api.com/v1/*
    response: typing.Optional[str] = None
    # wildcard pattern, e.g. *.api.com/v1/*
    request: typing.Optional[str] = None
