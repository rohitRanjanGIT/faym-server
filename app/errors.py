"""Domain errors, each mapped to an HTTP status by the API layer."""


class DomainError(Exception):
    """Base class for expected, client-facing business-rule violations."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404


class AlreadyReconciledError(DomainError):
    status_code = 409


class AlreadyExistsError(DomainError):
    """A resource with the same identifier already exists (e.g. a user)."""

    status_code = 409


class InvalidStatusError(DomainError):
    status_code = 400


class WithdrawalTooSoonError(DomainError):
    """A user may make only one withdrawal every 24 hours."""

    status_code = 429


class InsufficientBalanceError(DomainError):
    status_code = 422


class InvalidWithdrawalStateError(DomainError):
    status_code = 409


class AuthError(DomainError):
    """Missing/invalid credentials or token."""

    status_code = 401


class ForbiddenError(DomainError):
    """Authenticated but not allowed to perform this action."""

    status_code = 403
