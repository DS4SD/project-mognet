from enum import Enum


class OutputFormat(str, Enum):
    """CLI output format"""

    TEXT = "text"
    JSON = "json"


class LogLevel(Enum):
    """Log Level"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
