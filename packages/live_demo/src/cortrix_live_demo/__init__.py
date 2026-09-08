"""Cortrix live three-path implementation candidate."""

from .config import RuntimeConfig, load_config, validate_config
from .contracts import contract_mapping, validate_fixture_set


def status(*args, **kwargs):
    from .cli import status as implementation
    return implementation(*args, **kwargs)


def provision(*args, **kwargs):
    from .provision import provision as implementation
    return implementation(*args, **kwargs)


def serve(*args, **kwargs):
    from .server import serve as implementation
    return implementation(*args, **kwargs)

__all__ = ["RuntimeConfig", "contract_mapping", "load_config", "provision", "serve", "status", "validate_config", "validate_fixture_set"]
