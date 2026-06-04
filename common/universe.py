"""Helpers for resolving named symbol universes from configuration."""

from __future__ import annotations


def _upper_symbol_list(values):
    if not values:
        return []
    return [str(symbol).upper() for symbol in values if str(symbol).strip()]


def get_named_universe_sets(config):
    getter = getattr(config, "get", None)
    raw = getter("universe", "symbol_sets", default={}) if callable(getter) else {}
    return {
        str(name): _upper_symbol_list(symbols)
        for name, symbols in dict(raw or {}).items()
        if _upper_symbol_list(symbols)
    }


def get_named_universe(config, name):
    if not name:
        return []
    return list(get_named_universe_sets(config).get(str(name), []))


def resolve_symbols_from_config(
    config,
    *,
    explicit_paths=None,
    active_name_paths=None,
):
    """Resolve the active symbol list from explicit symbols or a named universe."""

    getter = getattr(config, "get", None)
    if callable(getter):
        for path in list(explicit_paths or []):
            configured = getter(*path, default=None)
            symbols = _upper_symbol_list(configured)
            if symbols:
                return symbols

        for path in list(active_name_paths or []):
            universe_name = getter(*path, default=None)
            symbols = get_named_universe(config, universe_name)
            if symbols:
                return symbols

        top_level_symbols = _upper_symbol_list(getter("universe", "symbols", default=None))
        if top_level_symbols:
            return top_level_symbols

        active_name = getter("universe", "active_set", default=None)
        named_symbols = get_named_universe(config, active_name)
        if named_symbols:
            return named_symbols

    return []
