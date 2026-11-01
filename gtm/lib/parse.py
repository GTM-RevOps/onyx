"""Turn YAML and JSON values into typed data."""

from __future__ import annotations


class ConfigError(Exception):
    """The GTM files or an Onyx response do not match the expected shape."""


def as_dict(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{what} must be a mapping")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ConfigError(f"{what} has a non-text key")
        result[key] = item
    return result


def as_list(value: object, what: str) -> list[object]:
    if not isinstance(value, list):
        raise ConfigError(f"{what} must be a list")
    return list(value)


def as_str(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{what} must be text")
    return value


def as_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{what} must be an integer")
    return value


def as_bool(value: object, what: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{what} must be true or false")
    return value


def require_key(mapping: dict[str, object], key: str, what: str) -> object:
    if key not in mapping:
        raise ConfigError(f"{what} is missing {key}")
    return mapping[key]


def str_list(value: object, what: str) -> tuple[str, ...]:
    return tuple(as_str(item, what) for item in as_list(value, what))
