class PanelError(Exception):
    """Base class for all panel-integration errors."""


class PanelUnavailable(PanelError):
    """Network failure, timeout, or 5xx — transient, safe to retry."""


class PanelAuthError(PanelError):
    """Admin credentials rejected or token could not be obtained."""


class PanelNotFound(PanelError):
    """The requested panel user / resource does not exist (404)."""


class PanelValidationError(PanelError):
    """The panel rejected the request payload (4xx other than 401/404)."""

    def __init__(self, message, *, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PanelConflict(PanelValidationError):
    """The panel user already exists (409)."""
