import json
import typing
from dataclasses import dataclass, fields


@dataclass
class DTOBase:
    """Only python basic types are supported: str, int, float, bool, dict, list."""

    @staticmethod
    def _ensure_bool_string(value: str) -> bool:
        return value.lower() in {"1", "true", "yes", "on"}

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> typing.Self:
        field_types = {f.name: f.type for f in fields(cls)}
        init_data = {}
        for key, value in data.items():
            if key in field_types:
                expected_type = field_types[key]
                if expected_type is str and type(value) is str:
                    if expected_type is int:
                        value = int(value)
                    elif expected_type is float:
                        value = float(value)
                    elif expected_type is bool:
                        value = cls._ensure_bool_string(value)
                    elif expected_type is dict or expected_type is list:
                        value = json.loads(value)
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
    wait_tag: str = ""
    cookies: typing.Optional[typing.Dict[str, str]] = None
    user_agent: str = ""
    extra_headers: typing.Optional[typing.Dict[str, str]] = None
    incognito_args: typing.Optional[typing.Dict[str, typing.Any]] = None


@dataclass
class JsDTO(DTOBase):
    """Parameters for executing JavaScript."""

    url: str
    js: str
    value_path: str = "result.result"
    wait_tag: str = ""
