class ChromeException(Exception):
    pass


class ChromeValueError(ValueError, ChromeException):
    pass


class ChromeRuntimeError(RuntimeError, ChromeException):
    pass


class ChromeTypeError(TypeError, ChromeException):
    pass


class TabConnectionError(ChromeRuntimeError):
    pass


class ChromeProcessMissingError(ChromeRuntimeError):
    '{"method":"Inspector.detached","params":{"reason":"Render process gone."},"sessionId":"9B732FA5900F6CE37B7B647D99B74897"}'

    pass
