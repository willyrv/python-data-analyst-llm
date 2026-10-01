"""Configuration lue depuis l'environnement. Aucun secret n'est codé en dur."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
# Clés des fournisseurs cloud. Le fichier est ignoré par git et lisible seulement par l'utilisateur.
load_dotenv(ROOT / ".secrets" / "llm-api-keys.env")


class Settings(BaseModel):
    """Paramètres de démo. Les valeurs UI peuvent surcharger température et tours."""

    openai_base_url: str = "http://localhost:8000/v1"
    openai_api_key: str = "dummy"
    model_name: str = "local-model"
    database_url: str = "postgresql+psycopg://olist_ro:olist_ro@localhost:5432/olist"
    database_admin_url: str = "postgresql+psycopg://olist:olist@localhost:5432/olist"
    readonly_db_user: str = "olist_ro"
    readonly_db_password: str = "olist_ro"
    debug: bool = False
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tool_rounds: int = Field(default=6, ge=1, le=12)
    llm_timeout_s: float = Field(default=120.0, gt=0)
    sql_row_limit: int = Field(default=200, ge=1, le=5000)
    sql_timeout_ms: int = Field(default=15000, ge=1000, le=120000)
    chart_dir: Path = Field(default=ROOT / "outputs" / "charts")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        model_name=os.getenv("MODEL_NAME", "local-model"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://olist_ro:olist_ro@localhost:5432/olist",
        ),
        database_admin_url=os.getenv(
            "DATABASE_ADMIN_URL",
            "postgresql+psycopg://olist:olist@localhost:5432/olist",
        ),
        readonly_db_user=os.getenv("READONLY_DB_USER", "olist_ro"),
        readonly_db_password=os.getenv("READONLY_DB_PASSWORD", "olist_ro"),
        debug=_as_bool(os.getenv("DEBUG"), False),
        temperature=float(os.getenv("TEMPERATURE", "0.1")),
        max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "6")),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "120")),
        sql_row_limit=int(os.getenv("SQL_ROW_LIMIT", "200")),
        sql_timeout_ms=int(os.getenv("SQL_TIMEOUT_MS", "15000")),
        chart_dir=Path(os.getenv("CHART_DIR", str(ROOT / "outputs" / "charts"))),
    )
