import warnings

warnings.warn(
    "The 'ichrome.web.routers' module is deprecated and will be removed in a future release. "
    "Use `ichrome.http` instead which handled with aiohttp.",
    DeprecationWarning,
    stacklevel=2,
)
