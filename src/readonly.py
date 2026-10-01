"""Rôle PostgreSQL limité au SELECT.

Appelé par `scripts/create_readonly_user.py` et à la fin du chargement,
pour que les droits suivent les tables recréées.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from src.config import Settings, get_settings
from src.database import admin_engine, database_name

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
_PASSWORD = re.compile(r"[A-Za-z0-9_@.+-]{1,64}")


def grant_readonly(settings: Settings | None = None) -> str:
    """Crée ou met à jour le rôle lecture seule et ne lui laisse que SELECT."""
    settings = settings or get_settings()
    user = settings.readonly_db_user
    password = settings.readonly_db_password
    if not _IDENT.fullmatch(user):
        raise ValueError("READONLY_DB_USER doit être un identifiant SQL simple.")
    if not _PASSWORD.fullmatch(password):
        raise ValueError("READONLY_DB_PASSWORD : utilisez seulement A-Z, a-z, 0-9, _ @ . + -")
    dbname = database_name(settings.database_admin_url)
    if not _IDENT.fullmatch(dbname):
        raise ValueError(f"Nom de base inattendu : {dbname}")

    engine = admin_engine(settings)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
            {"name": user},
        ).scalar()
        if not exists:
            conn.exec_driver_sql(f"CREATE ROLE {user} LOGIN PASSWORD '{password}'")
        else:
            conn.exec_driver_sql(f"ALTER ROLE {user} WITH LOGIN PASSWORD '{password}'")
        conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE {dbname} TO {user}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {user}")
        conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {user}")
        conn.exec_driver_sql(
            "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
            f"ON ALL TABLES IN SCHEMA public FROM {user}"
        )
    return user
