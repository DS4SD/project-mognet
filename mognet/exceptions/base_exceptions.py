class MognetError(Exception):
    """Base class for all Mognet errors"""


class ImproperlyConfigured(MognetError):
    """Base class for configuration-based errors"""


class CouldNotSubmit(MognetError):
    """The Request could not be submitted"""


class ConnectionError(MognetError):
    """Base class for connection errors"""


class NotConnected(ConnectionError):
    """Not connected. Either call connect(), or use a context manager"""
