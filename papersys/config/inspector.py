"""Utilities for inspecting and validating configuration files."""

from __future__ import annotations

from pathlib import Path
from types import UnionType
from typing import Any, Iterable, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from .app import AppConfig
from .base import load_config


ConfigModel = AppConfig


class ConfigInspectionError(RuntimeError):
    """Raised when configuration inspection fails unexpectedly."""


def check_config(path: Path, *, config_cls: type[ConfigModel] = ConfigModel) -> tuple[dict[str, Any], int, ConfigModel | None]:
    """Validate the configuration file and collect warnings.

    Returns a tuple of ``(result_dict, exit_code, config_instance_or_None)``.
    """

    try:
        config = load_config(config_cls, path)
    except FileNotFoundError as exc:
        return (
            {
                "status": "error",
                "config_path": str(path),
                "error": {
                    "type": "missing_file",
                    "message": str(exc),
                },
            },
            2,
            None,
        )
    except ValidationError as exc:
        return (
            {
                "status": "error",
                "config_path": str(path),
                "error": {
                    "type": "validation_error",
                    "message": "Configuration validation failed",
                    "details": [
                        {
                            "loc": _format_error_location(err["loc"]),
                            "message": err["msg"],
                            "type": err["type"],
                        }
                        for err in exc.errors()
                    ],
                },
            },
            3,
            None,
        )
    except PermissionError as exc:
        return (
            {
                "status": "error",
                "config_path": str(path),
                "error": {
                    "type": "permission_error",
                    "message": str(exc),
                },
            },
            2,
            None,
        )
    except ValueError as exc:
        return (
            {
                "status": "error",
                "config_path": str(path),
                "error": {
                    "type": "invalid_format",
                    "message": str(exc),
                },
            },
            1,
            None,
        )
    except Exception as exc:  # pragma: no cover - unexpected failures
        raise ConfigInspectionError("Unexpected configuration inspection error") from exc

    warnings = _collect_warnings(config)
    result = {
        "status": "ok",
        "config_path": str(path),
        "warnings": warnings,
    }
    return result, 0, config


def explain_config(*, config_cls: type[ConfigModel] = ConfigModel) -> list[dict[str, Any]]:
    """Describe configuration fields for documentation purposes."""

    documentation: list[dict[str, Any]] = []
    visited: set[type[BaseModel]] = set()

    def _walk(model_cls: type[BaseModel], prefix: str = "") -> None:
        if model_cls in visited:
            return
        visited.add(model_cls)

        for field_name, field in model_cls.model_fields.items():
            entry = {
                "name": f"{prefix}{field_name}",
                "type": _format_annotation(field.annotation),
                "required": field.is_required(),
                "default": _format_default(field),
                "description": field.description or "",
            }
            documentation.append(entry)

            for nested_cls, nested_prefix in _iter_nested_models(field, base_prefix=f"{prefix}{field_name}"):
                _walk(nested_cls, nested_prefix)

    _walk(config_cls)
    return documentation


def _format_error_location(location: Iterable[Union[int, str]]) -> str:
    return ".".join(str(part) for part in location)


def _collect_warnings(config: ConfigModel) -> list[str]:
    warnings: list[str] = []

    if config.data_root is not None:
        warnings.append("'data_root' is deprecated; prefer module-specific base paths")
    if config.embedding_models:
        warnings.append("'embedding_models' is legacy and will be removed in future versions")
    if config.scheduler_enabled and config.scheduler is None:
        warnings.append("'scheduler_enabled' is true but no scheduler block is configured")
    if not config.llms:
        warnings.append("No LLM configurations defined; summary pipeline may not function")

    return warnings


def _format_annotation(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type):
            return annotation.__name__
        return repr(annotation).replace("typing.", "")

    args = get_args(annotation)
    if origin in {Union, UnionType}:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: E721
        if len(non_none) == 1 and len(args) == 2:
            return f"Optional[{_format_annotation(non_none[0])}]"
        joined = ", ".join(_format_annotation(arg) for arg in args)
        return f"Union[{joined}]"

    origin_name = getattr(origin, "__name__", repr(origin).replace("typing.", ""))
    if args:
        joined_args = ", ".join(_format_annotation(arg) for arg in args)
        return f"{origin_name}[{joined_args}]"
    return origin_name


def _format_default(field: FieldInfo) -> Any:
    if field.default_factory is not None:
        try:
            value = field.default_factory()
        except Exception:  # pragma: no cover - factory failure is unexpected
            return "<factory>"
        return _stringify_default(value)
    if field.is_required():
        return None
    return _stringify_default(field.default)


def _stringify_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, (list, tuple)):
        return [_stringify_default(item) for item in value]
    if isinstance(value, dict):
        return {key: _stringify_default(val) for key, val in value.items()}
    return value


def _iter_nested_models(field: FieldInfo, *, base_prefix: str) -> list[tuple[type[BaseModel], str]]:
    nested: list[tuple[type[BaseModel], str]] = []
    annotation = field.annotation
    origin = get_origin(annotation)
    if origin is None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested.append((annotation, f"{base_prefix}."))
        return nested

    args = get_args(annotation)
    if origin in {Union, UnionType}:
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                nested.append((arg, f"{base_prefix}."))
        return nested

    if origin in {list, tuple, set}:  # handle homogeneous collections
        if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
            nested.append((args[0], f"{base_prefix}[]."))
        return nested

    if origin is dict:
        if len(args) == 2 and isinstance(args[1], type) and issubclass(args[1], BaseModel):
            nested.append((args[1], f"{base_prefix}{{}}."))
        return nested

    return nested


__all__ = ["check_config", "explain_config", "ConfigInspectionError"]
