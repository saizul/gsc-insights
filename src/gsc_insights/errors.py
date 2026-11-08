"""Exception types raised by gsc-insights."""


class GscInsightsError(Exception):
    """Base class for all expected, user-facing errors."""


class LoadError(GscInsightsError):
    """An export could not be found, read or understood."""


class ConfigError(GscInsightsError):
    """The configuration file or one of its values is invalid."""
