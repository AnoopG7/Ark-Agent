"""Errors raised by ops repositories. Messages are written to be shown to the agent and users."""


class RepositoryError(Exception):
    """Base class for all repository errors."""


class NotFoundError(RepositoryError):
    """A referenced ward, depot, route, team or task does not exist."""


class InsufficientStockError(RepositoryError):
    """A depot does not hold enough available stock for an allocation."""


class ConflictError(RepositoryError):
    """The operation conflicts with current state (blocked route, team busy, mismatched route)."""
