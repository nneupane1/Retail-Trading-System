"""Config-driven debug output helpers."""

import builtins
from contextlib import contextmanager

from config import AppConfig


_DEBUG_ENABLED = None
_DEBUG_OVERRIDE_STACK = []


def _read_debug_flag(config):
    getter = getattr(config, "get", None)
    if callable(getter):
        value = getter("app", "debug", default=True)
        return True if value is None else bool(value)

    try:
        return bool(config.require("app", "debug"))
    except Exception:
        return True


def configure_debug(enabled=None, config=None):
    """
    Set or load the global debug-output flag.
    """

    global _DEBUG_ENABLED

    if enabled is not None:
        _DEBUG_ENABLED = bool(enabled)
        return _DEBUG_ENABLED

    source_config = config or AppConfig.load()
    _DEBUG_ENABLED = _read_debug_flag(source_config)
    return _DEBUG_ENABLED


def is_debug_enabled():
    """
    Return whether debug output is currently enabled.
    """

    global _DEBUG_ENABLED

    if _DEBUG_OVERRIDE_STACK:
        return _DEBUG_OVERRIDE_STACK[-1]

    if _DEBUG_ENABLED is None:
        configure_debug()

    return _DEBUG_ENABLED


@contextmanager
def override_debug(enabled):
    """
    Temporarily override the global debug-output state.
    """

    _DEBUG_OVERRIDE_STACK.append(bool(enabled))
    try:
        yield
    finally:
        _DEBUG_OVERRIDE_STACK.pop()


def debug_print(*args, **kwargs):
    """
    Print only when debug output is enabled.
    """

    if is_debug_enabled():
        builtins.print(*args, **kwargs)
