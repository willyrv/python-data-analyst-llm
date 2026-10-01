"""Accès PostgreSQL.

L'application ouvre une session en lecture seule, avec un timeout.
Le chargement des CSV utilise un moteur séparé, jamais exposé au LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from src.config import Settings, get_settings


@dataclass
class DatabaseStatus:
    ok: bool
    message: str
    user: str | None = None


@lru_cache
def get_engine(url: str, readonly: bool, timeout_ms: int) -> Engine:
    """Crée un moteur SQLAlchemy.

    En lecture seule, PostgreSQL refuse les écritures même si un SQL
    dangereux passait outre le validateur Python.
    """
    # connect_timeout évite de figer Streamlit si PostgreSQL n'est pas lancé.
    connect_args: dict[str, object] = {"connect_timeout": 3}
    if readonly:
        connect_args["options"] = (
            f"-c statement_timeout={int(timeout_ms)} "
            "-c default_transaction_read_only=on"
        )
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def app_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    return get_engine(settings.database_url, True, settings.sql_timeout_ms)


def admin_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    return get_engine(settings.database_admin_url, False, settings.sql_timeout_ms)


def database_status(settings: Settings | None = None) -> DatabaseStatus:
    settings = settings or get_settings()
    try:
        with app_engine(settings).connect() as conn:
            user = conn.execute(text("SELECT current_user")).scalar()
            conn.execute(text("SELECT 1"))
        return DatabaseStatus(ok=True, message="connecté", user=str(user))
    except Exception as exc:  # noqa: BLE001 - message propre pour la démo
        return DatabaseStatus(
            ok=False,
            message=redact_secrets(str(exc).splitlines()[0], settings),
        )


def database_name(url: str) -> str:
    parsed = make_url(url)
    if not parsed.database:
        raise ValueError(f"URL sans nom de base : {url}")
    return parsed.database


def redact_secrets(message: str, settings: Settings | None = None) -> str:
    """Retire les mots de passe des URL si un message d'erreur les répète."""
    settings = settings or get_settings()
    passwords: list[str] = []
    for url in (settings.database_url, settings.database_admin_url):
        try:
            password = make_url(url).password
        except Exception:  # noqa: BLE001 - une URL illisible ne doit pas masquer l'erreur d'origine
            continue
        if password:
            passwords.append(password)
    redacted = message
    for password in sorted(set(passwords), key=len, reverse=True):
        redacted = redacted.replace(password, "***")
    return redacted
