class CaptureError(Exception):
    """Base error with a safe user-facing message."""


class ValidationError(CaptureError):
    pass


class ConfirmationError(CaptureError):
    pass


class MigrationError(CaptureError):
    pass

