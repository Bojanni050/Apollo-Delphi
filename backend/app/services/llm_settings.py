"""LLM settings chosen in the UI, stored in the database and layered over the environment.

The environment still provides the defaults; a row in ``app_settings`` wins. Applying
a change mutates the cached ``Settings`` object and drops the cached providers, so it
takes effect on the next call without a restart.

API keys are stored in the local database and are write-only: nothing here or in the
API ever returns one, only whether one is set.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import set_llm_provider
from app.core.logging import get_logger
from app.models.app_setting import AppSetting

log = get_logger(__name__)

PROVIDERS = ("mock", "openai", "anthropic")

#: setting key -> type used to read it back from its stored string
FIELDS: dict[str, type] = {
    "llm_provider": str,
    "llm_model": str,
    "background_llm_model": str,
    "llm_base_url": str,
    "llm_timeout_seconds": float,
    "openai_api_key": str,
    "anthropic_api_key": str,
}
SECRETS = frozenset({"openai_api_key", "anthropic_api_key"})


class SettingsError(ValueError):
    pass


def _apply(values: dict[str, object]) -> None:
    settings = get_settings()
    for key, value in values.items():
        setattr(settings, key, value)
    set_llm_provider(None)


def load_overrides(db: Session) -> None:
    """Apply everything stored in the database on top of the environment (call at startup)."""
    values: dict[str, object] = {}
    for row in db.query(AppSetting).all():
        kind = FIELDS.get(row.key)
        if kind is None:
            continue
        try:
            values[row.key] = kind(row.value)
        except ValueError:
            log.warning("Ignoring unreadable stored setting %s", row.key)
    _apply(values)


def validate(updates: dict[str, object]) -> None:
    if "llm_provider" in updates and updates["llm_provider"] not in PROVIDERS:
        raise SettingsError(f"Provider must be one of: {', '.join(PROVIDERS)}")
    base_url = updates.get("llm_base_url")
    if base_url and not str(base_url).startswith(("http://", "https://")):
        raise SettingsError("Base URL must start with http:// or https://")
    timeout = updates.get("llm_timeout_seconds")
    if timeout is not None and not (1 <= float(timeout) <= 1800):  # type: ignore[arg-type]
        raise SettingsError("Timeout must be between 1 and 1800 seconds")


def save(db: Session, updates: dict[str, object]) -> None:
    """Persist and apply. Only keys present in ``updates`` are touched; unknown keys are rejected."""
    unknown = set(updates) - set(FIELDS)
    if unknown:
        raise SettingsError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
    validate(updates)
    for key, value in updates.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=str(value)))
        else:
            row.value = str(value)
    db.commit()
    _apply(updates)
