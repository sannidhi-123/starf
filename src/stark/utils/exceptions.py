"""Exceptions and domain error types for STARK Detection Pipeline."""


class StarkError(Exception):
    """Base exception for all STARK errors."""

    pass


class RuleConfigError(StarkError):
    """Raised when rule configuration file (rules.yaml) is missing or malformed."""

    pass
