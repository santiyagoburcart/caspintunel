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


class PanelNameTaken(PanelError):
    """The account name already exists on the panel and is not ours to take
    (someone else's account, e.g. a reseller's). We never attach to it."""

    def __init__(self, username, *, owner=None):
        self.username, self.owner = username, owner
        super().__init__(f"the account name '{username}' already exists on the panel"
                         + (f" (admin {owner})" if owner else "") + " — choose another name")


class PanelLinkNeedsConfirmation(PanelError):
    """Linking an existing account that belongs to another panel admin needs an explicit choice."""

    def __init__(self, username, *, owner):
        self.username, self.owner = username, owner
        super().__init__(f"panel account {username} belongs to admin {owner}, not this panel's admin — "
                         "confirm explicitly to link it")
