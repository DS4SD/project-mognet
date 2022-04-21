from mognet.exceptions.base_exceptions import MognetError


class BrokerError(MognetError):
    pass


class QueueNotFound(BrokerError):
    pass
