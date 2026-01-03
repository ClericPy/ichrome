import warnings

warnings.warn(
    "The 'ichrome.routers' module is deprecated and will be removed in a future release. "
    "Use `ichrome.http` instead which handled with aiohttp.",
    DeprecationWarning,
    stacklevel=2,
)
