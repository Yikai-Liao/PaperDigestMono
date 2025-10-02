"""Helper utilities for configuration handling."""

from __future__ import annotations

import os

_ENV_PREFIX = "env:"


def resolve_env_reference(value: str | None, *, required: bool = True) -> str | None:
    """Resolve values that reference environment variables.

    Accepts strings in the form ``"env:VAR_NAME"`` and returns the value from
    ``os.environ``. When ``required`` is ``True`` (default) and the variable is
    missing or empty, an :class:`EnvironmentError` is raised. Plain strings are
    returned unchanged, and ``None`` values are passed through.
    """

    if value is None:
        return None
    if not value.startswith(_ENV_PREFIX):
        return value

    var_name = value.split(":", 1)[1]
    resolved = os.getenv(var_name)
    if resolved:
        return resolved
    if required:
        raise EnvironmentError(f"Environment variable '{var_name}' is not set or empty")
    return None


__all__ = ["resolve_env_reference"]
