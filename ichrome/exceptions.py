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
