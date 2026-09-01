class CaptureError(Exception):
    """Base error with a safe user-facing message."""


class ValidationError(CaptureError):
    pass


class ConfirmationError(CaptureError):
    pass


class MigrationError(CaptureError):
    pass


class AuthorizationError(CaptureError):
    """Enterprise capture authorization is missing, invalid, forged, or out of scope.

    Always fail closed: this error means nothing was persisted.
    """


class StorageError(CaptureError):
    """Storage adapter failure with a safe, deployment-agnostic message."""


class CaptureStorageError(CaptureError):
    """The task itself completed, but persisting the capture failed.

    Carries the honest capture status so callers never confuse a finished
    business task with a finished data-persistence step.
    """

    def __init__(self, message, status="TASK_COMPLETED_CAPTURE_FAILED"):
        super().__init__(message)
        self.status = status
