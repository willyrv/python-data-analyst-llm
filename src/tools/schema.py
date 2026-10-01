"""Inspection du schéma, table par table.

Sans nom de table : liste des tables et des jointures.
Avec un nom : colonnes et types de cette table seulement.
Le modèle ne reçoit donc pas tout le catalogue à chaque question.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.config import Settings, get_settings
from src.tools.sql import QueryResult, execute_parameterized

# Documentation de jointure, pas un résultat inventé : ce sont les clés du chargement.
RELATIONS = (
    "orders.customer_id -> customers.customer_id",
    "order_items.order_id -> orders.order_id",
    "order_items.product_id -> products.product_id",
    "order_items.seller_id -> sellers.seller_id",
    "payments.order_id -> orders.order_id",
    "reviews.order_id -> orders.order_id",
    "products.product_category_name -> product_categories.product_category_name",
)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class SchemaArgs(BaseModel):
    table: str | None = Field(default=None, description="Nom de table, ou vide pour la liste.")


def inspect_database_schema(arguments: dict, settings: Settings | None = None) -> tuple[str, str | None]:
    """Retourne (texte pour le LLM, erreur éventuelle)."""
    args = SchemaArgs.model_validate(arguments or {})
    settings = settings or get_settings()
    if args.table:
        return _one_table(args.table, settings)
    return _catalog(settings), None


def _catalog(settings: Settings) -> str:
    tables = execute_parameterized(
        """
        SELECT t.table_name,
               COALESCE(c.reltuples, 0)::bigint AS estimated_rows
        FROM information_schema.tables AS t
        LEFT JOIN pg_namespace AS n ON n.nspname = t.table_schema
        LEFT JOIN pg_class AS c ON c.relname = t.table_name AND c.relnamespace = n.oid
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
        """,
        {},
        max_rows=100,
        settings=settings,
    )
    lines = ["Tables disponibles (nombre de lignes estimé par PostgreSQL) :"]
    if not tables.rows:
        lines.append("(aucune table — le dataset Olist n'a peut-être pas été chargé)")
    for row in tables.rows:
        lines.append(f"- {row['table_name']} (~{row['estimated_rows']} lignes)")
    lines.append("")
    lines.append("Relations :")
    lines.extend(f"- {relation}" for relation in RELATIONS)
    lines.append("")
    lines.append("Pour les colonnes d'une table, rappelle cet outil avec son nom.")
    return "\n".join(lines)


def _one_table(table: str, settings: Settings) -> tuple[str, str | None]:
    if not _IDENT.fullmatch(table):
        return "", f"Nom de table invalide : {table!r}."
    known = execute_parameterized(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """,
        {},
        max_rows=200,
        settings=settings,
    )
    names = {row["table_name"] for row in known.rows}
    if table not in names:
        return "", f"Table inconnue : {table}. Tables : {', '.join(sorted(names)) or '(aucune)'}."
    columns: QueryResult = execute_parameterized(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table
        ORDER BY ordinal_position
        """,
        {"table": table},
        max_rows=200,
        settings=settings,
    )
    lines = [f"Table {table} :"]
    for row in columns.rows:
        lines.append(f"- {row['column_name']} {row['data_type']}")
    related = [relation for relation in RELATIONS if relation.startswith(f"{table}.") or f"-> {table}." in relation]
    if related:
        lines.append("Relations :")
        lines.extend(f"- {relation}" for relation in related)
    return "\n".join(lines), None
