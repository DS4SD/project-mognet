class GracefulShutdown(BaseException):
    """If this exception is raised from a coroutine, the Mognet app running from the CLI will be gracefully closed"""
