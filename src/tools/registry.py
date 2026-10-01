"""Registre des outils.

Le LLM ne reçoit que les schémas. L'exécution passe par `dispatch`,
qui valide les arguments puis appelle le code Python correspondant.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings
from src.database import redact_secrets
from src.serialize import to_jsonable
from src.tools.analysis import analyze_dataframe
from src.tools.charts import create_chart
from src.tools.reviews import search_reviews
from src.tools.schema import inspect_database_schema
from src.tools.sql import QueryArgs, execute_select, format_table
from src.tools.sql_safety import SqlSafetyError

_LLM_PREVIEW_ROWS = 20
_UI_PREVIEW_ROWS = 50


class ToolOutcome(BaseModel):
    content: str
    sql: str | None = None
    sql_origin: str | None = None
    columns: list[str] | None = None
    rows: list[dict[str, Any]] | None = None
    row_count: int | None = None
    chart_path: str | None = None
    analysis: str | None = None
    error: str | None = None


Handler = Callable[[dict, Settings], ToolOutcome]


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "inspect_database_schema",
                "description": (
                    "Décrit les tables Olist, ou les colonnes d'une table si `table` est fourni. "
                    "À utiliser quand une colonne ou une jointure n'est pas certaine."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": "Nom de table. Omettre pour lister les tables.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_database",
                "description": (
                    "Exécute un unique SELECT ou WITH ... SELECT en lecture seule. "
                    "Préfère les agrégations (SUM, AVG, COUNT, GROUP BY). "
                    "Le chiffre d'affaires est SUM(order_items.price), hors frais de port. "
                    "Au plus 200 lignes sont renvoyées."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "Requête SELECT PostgreSQL."}
                    },
                    "required": ["sql"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_dataframe",
                "description": (
                    "Calcule des statistiques pandas sur le résultat d'un SELECT. "
                    "Opérations : describe, quantiles, correlation, compare_groups, aggregate, time_series. "
                    "Pour le retard : delay_days = EXTRACT(EPOCH FROM "
                    "(order_delivered_customer_date - order_estimated_delivery_date)) / 86400.0, "
                    "puis correlation entre delay_days et review_score, "
                    "ou compare_groups sur un statut de retard."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "operation": {
                            "type": "string",
                            "enum": [
                                "describe",
                                "quantiles",
                                "correlation",
                                "compare_groups",
                                "aggregate",
                                "time_series",
                            ],
                        },
                        "column": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "group_by": {"type": "string"},
                        "value_column": {"type": "string"},
                        "agg": {
                            "type": "string",
                            "enum": ["mean", "median", "sum", "count", "min", "max"],
                        },
                        "date_column": {"type": "string"},
                        "freq": {"type": "string", "enum": ["D", "W", "ME"]},
                    },
                    "required": ["sql", "operation"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_chart",
                "description": (
                    "Trace un graphique matplotlib : bar, line, histogram, scatter ou boxplot. "
                    "Pour bar et line, le SELECT doit déjà être agrégé (peu de lignes). "
                    "x et y sont des noms de colonnes du SELECT."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "chart_type": {
                            "type": "string",
                            "enum": ["bar", "line", "histogram", "scatter", "boxplot"],
                        },
                        "x": {"type": "string"},
                        "y": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["sql", "chart_type", "x"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_reviews",
                "description": (
                    "Récupère des avis clients réels (texte portugais) via un filtre SQL. "
                    "Pour des clients en retard et insatisfaits : only_late=true et max_score=2. "
                    "N'invente aucun verbatim : cite uniquement les commentaires renvoyés."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "only_late": {
                            "type": "boolean",
                            "description": "Livraison après la date estimée.",
                        },
                        "max_score": {
                            "type": "integer",
                            "description": "Garde les notes inférieures ou égales à cette valeur (1-5).",
                        },
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Mots recherchés dans le commentaire, en portugais si besoin.",
                        },
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
    ]


def known_tool_names() -> set[str]:
    return {schema["function"]["name"] for schema in tool_schemas()}


def dispatch(name: str, arguments: dict | None, settings: Settings | None = None) -> ToolOutcome:
    """Valide puis exécute. Toute erreur devient un résultat d'outil, pas un crash."""
    settings = settings or get_settings()
    arguments = arguments or {}
    handler = _HANDLERS.get(name)
    if handler is None:
        known = ", ".join(sorted(known_tool_names()))
        return ToolOutcome(content=f"Outil inconnu : {name}. Outils : {known}.", error=f"Outil inconnu : {name}.")
    try:
        return handler(arguments, settings)
    except (ValidationError, SqlSafetyError, ValueError) as exc:
        message = _short_error(exc)
        return ToolOutcome(content=f"Erreur : {message}", error=message)
    except Exception as exc:  # noqa: BLE001 - le modèle doit voir l'échec et pouvoir réessayer
        message = redact_secrets(f"{type(exc).__name__}: {exc}".splitlines()[0], settings)
        return ToolOutcome(content=f"Erreur : {message}", error=message)


def _query_database(arguments: dict, settings: Settings) -> ToolOutcome:
    args = QueryArgs.model_validate(arguments)
    result = execute_select(args.sql, max_rows=settings.sql_row_limit, settings=settings)
    preview = format_table(result, limit=_LLM_PREVIEW_ROWS)
    content = f"{result.row_count} lignes renvoyées.\n{preview}"
    return ToolOutcome(
        content=content,
        sql=result.sql,
        sql_origin="model",
        columns=result.columns,
        rows=result.rows[:_UI_PREVIEW_ROWS],
        row_count=result.row_count,
    )


def _schema(arguments: dict, settings: Settings) -> ToolOutcome:
    text, error = inspect_database_schema(arguments, settings)
    if error:
        return ToolOutcome(content=f"Erreur : {error}", error=error)
    return ToolOutcome(content=text)


def _analysis(arguments: dict, settings: Settings) -> ToolOutcome:
    summary = analyze_dataframe(arguments, settings)
    payload = json.dumps(to_jsonable(summary), ensure_ascii=False, indent=2)
    return ToolOutcome(
        content=payload,
        sql=summary.get("sql"),
        sql_origin="model",
        analysis=str(summary.get("operation")),
    )


def _chart(arguments: dict, settings: Settings) -> ToolOutcome:
    summary = create_chart(arguments, settings)
    content = (
        f"Graphique {summary['chart_type']} créé à partir de {summary['rows']} lignes. "
        "Il est affiché à l'utilisateur. Décris-le sans inventer de valeurs absentes des outils."
    )
    return ToolOutcome(
        content=content,
        sql=summary.get("sql"),
        sql_origin="model",
        chart_path=summary.get("chart_path"),
        row_count=summary.get("rows"),
        analysis=summary.get("chart_type"),
    )


def _reviews(arguments: dict, settings: Settings) -> ToolOutcome:
    summary = search_reviews(arguments, settings)
    payload = json.dumps(to_jsonable(summary), ensure_ascii=False, indent=2)
    return ToolOutcome(
        content=payload,
        sql=summary.get("sql"),
        sql_origin="application",
        rows=summary.get("reviews"),
        row_count=summary.get("review_count"),
        analysis="search_reviews",
    )


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            loc = ".".join(str(item) for item in error.get("loc", ()))
            parts.append(f"{loc}: {error.get('msg')}")
        return redact_secrets("; ".join(parts) or str(exc))
    return redact_secrets(str(exc))


_HANDLERS: dict[str, Handler] = {
    "inspect_database_schema": _schema,
    "query_database": _query_database,
    "analyze_dataframe": _analysis,
    "create_chart": _chart,
    "search_reviews": _reviews,
}
