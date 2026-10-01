"""Exécution des SELECT validés, avec plafond de lignes."""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.config import Settings, get_settings
from src.database import app_engine
from src.serialize import to_jsonable
from src.tools.sql_safety import validate_readonly_sql


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    sql: str


class QueryArgs(BaseModel):
    sql: str = Field(min_length=1, max_length=8_000)


def execute_select(
    sql: str,
    *,
    max_rows: int,
    settings: Settings | None = None,
) -> QueryResult:
    """Valide puis exécute un SELECT. N'ouvre pas la base si le SQL est refusé."""
    safe_sql = validate_readonly_sql(sql)
    wrapped = f"SELECT * FROM ({safe_sql}) AS _safe_subq LIMIT {int(max_rows) + 1}"
    settings = settings or get_settings()
    with app_engine(settings).connect() as conn:
        columns, fetched = _fetch_literal_sql(conn, wrapped)

    truncated = len(fetched) > max_rows
    kept = fetched[:max_rows]
    rows = [
        {column: to_jsonable(value) for column, value in zip(columns, row, strict=True)}
        for row in kept
    ]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        sql=safe_sql,
    )


def execute_parameterized(
    sql: str,
    params: dict[str, Any],
    *,
    max_rows: int,
    settings: Settings | None = None,
) -> QueryResult:
    """Exécute un SQL écrit par l'application, avec paramètres liés.

    Ce chemin n'accepte pas le SQL du modèle. Les outils reviews et schema
    l'utilisent pour rester à l'abri des injections.
    """
    settings = settings or get_settings()
    with app_engine(settings).connect() as conn:
        result = conn.execute(text(sql), params)
        columns = list(result.keys())
        fetched = result.fetchmany(max_rows + 1)
    truncated = len(fetched) > max_rows
    kept = fetched[:max_rows]
    rows = [
        {column: to_jsonable(value) for column, value in zip(columns, row, strict=True)}
        for row in kept
    ]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        sql=sql,
    )


def result_to_frame(result: QueryResult) -> pd.DataFrame:
    frame = pd.DataFrame(result.rows, columns=result.columns)
    return coerce_dataframe(frame)


def coerce_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Convertit les colonnes numériques laissées en texte ou Decimal."""
    converted = frame.copy()
    for column in converted.columns:
        series = converted[column]
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            continue
        numeric = pd.to_numeric(series, errors="coerce")
        # On ne remplace que si la majorité des valeurs non vides était numérique.
        original_present = series.notna().sum()
        if original_present and numeric.notna().sum() >= original_present * 0.8:
            converted[column] = numeric
    return converted


def format_table(result: QueryResult, *, limit: int = 20) -> str:
    """Tableau compact pour le contexte du LLM. Ce n'est pas toute la table."""
    columns = result.columns
    shown = result.rows[:limit]
    if not columns:
        return "Aucun résultat."
    header = " | ".join(columns)
    separator = " | ".join("---" for _ in columns)
    lines = [header, separator]
    for row in shown:
        cells = [_clip(row.get(column)) for column in columns]
        lines.append(" | ".join(cells))
    extra = ""
    if result.truncated:
        extra = (
            f"\nRésultat tronqué à {result.row_count} lignes. "
            "Agrège dans le SQL (GROUP BY, AVG, SUM, COUNT) pour un chiffre exact."
        )
    elif result.row_count > len(shown):
        extra = f"\n{result.row_count} lignes au total, {len(shown)} affichées ici."
    return "\n".join(lines) + extra


def _clip(value: Any, width: int = 80) -> str:
    text_value = "" if value is None else str(value).replace("\n", " ").replace("|", "/")
    if len(text_value) > width:
        return text_value[: width - 1] + "…"
    return text_value


def _fetch_literal_sql(conn: Any, sql: str) -> tuple[list[str], list[Any]]:
    """Exécute un SQL littéral, sans que psycopg lise les '%' comme des paramètres.

    Avec une liste de paramètres vide, psycopg interprète '%' (LIKE, modulo).
    Le curseur DBAPI est donc appelé sans paramètres : le texte validé part tel quel.
    """
    driver = conn.connection.driver_connection
    cursor = driver.cursor()
    try:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = list(cursor.fetchall())
    finally:
        cursor.close()
    return columns, rows
