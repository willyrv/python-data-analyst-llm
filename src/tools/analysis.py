"""Opérations pandas explicites. Pas de exec(), pas de Python arbitraire."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from src.config import Settings, get_settings
from src.serialize import to_jsonable
from src.tools.sql import execute_select, result_to_frame

Operation = Literal["describe", "quantiles", "correlation", "compare_groups", "aggregate", "time_series"]
AggName = Literal["mean", "median", "sum", "count", "min", "max"]

_ANALYSIS_ROW_LIMIT = 100_000


class AnalysisArgs(BaseModel):
    sql: str
    operation: Operation
    column: str | None = None
    columns: list[str] | None = None
    group_by: str | None = None
    value_column: str | None = None
    agg: AggName = "mean"
    date_column: str | None = None
    freq: Literal["D", "W", "ME"] = "ME"

    @model_validator(mode="before")
    @classmethod
    def coerce_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        columns = data.get("columns")
        if isinstance(columns, str):
            data["columns"] = [columns]
        return data


def analyze_dataframe(arguments: dict, settings: Settings | None = None) -> dict[str, Any]:
    args = AnalysisArgs.model_validate(arguments)
    settings = settings or get_settings()
    result = execute_select(args.sql, max_rows=_ANALYSIS_ROW_LIMIT, settings=settings)
    frame = result_to_frame(result)
    summary = run_operation(frame, args)
    summary["rows_analyzed"] = int(len(frame))
    summary["truncated"] = result.truncated
    summary["sql"] = result.sql
    return summary


def run_operation(frame: pd.DataFrame, args: AnalysisArgs) -> dict[str, Any]:
    """Point testable sans base de données."""
    if frame.empty:
        raise ValueError("La requête n'a renvoyé aucune ligne.")
    if args.operation == "describe":
        return _describe(frame)
    if args.operation == "quantiles":
        return _quantiles(frame, _require(args.column, "column"))
    if args.operation == "correlation":
        return _correlation(frame, args.columns)
    if args.operation == "compare_groups":
        return _compare_groups(
            frame,
            _require(args.group_by, "group_by"),
            _require(args.value_column, "value_column"),
        )
    if args.operation == "aggregate":
        return _aggregate(
            frame,
            _require(args.group_by, "group_by"),
            _require(args.value_column, "value_column"),
            args.agg,
        )
    if args.operation == "time_series":
        return _time_series(
            frame,
            _require(args.date_column, "date_column"),
            _require(args.value_column, "value_column"),
            args.freq,
        )
    raise ValueError(f"Opération inconnue : {args.operation}")


def _describe(frame: pd.DataFrame) -> dict[str, Any]:
    numeric = frame.select_dtypes(include="number")
    if numeric.empty:
        raise ValueError("Aucune colonne numérique à décrire.")
    described = numeric.describe().round(4)
    return {
        "operation": "describe",
        "stats": to_jsonable(described.to_dict()),
    }


def _quantiles(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    series = _numeric_series(frame, column).dropna()
    if series.empty:
        raise ValueError(f"Colonne vide : {column}")
    probs = [0.1, 0.25, 0.5, 0.75, 0.9]
    values = series.quantile(probs)
    return {
        "operation": "quantiles",
        "column": column,
        "count": int(series.shape[0]),
        "quantiles": {str(prob): float(values.loc[prob]) for prob in probs},
    }


def _correlation(frame: pd.DataFrame, columns: list[str] | None) -> dict[str, Any]:
    numeric = frame.select_dtypes(include="number")
    if columns:
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise ValueError(f"Colonnes absentes : {', '.join(missing)}. Présentes : {list(frame.columns)}")
        numeric = frame[columns].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.dropna(axis=1, how="all")
    if numeric.shape[1] < 2:
        raise ValueError("La corrélation demande au moins deux colonnes numériques.")
    corr = numeric.corr(numeric_only=True).round(4)
    return {
        "operation": "correlation",
        "columns": list(corr.columns),
        "correlation": to_jsonable(corr.to_dict()),
        "rows_used": int(numeric.dropna().shape[0]),
    }


def _compare_groups(frame: pd.DataFrame, group_by: str, value_column: str) -> dict[str, Any]:
    _ensure_columns(frame, [group_by, value_column])
    working = frame[[group_by, value_column]].copy()
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    grouped = working.groupby(group_by, dropna=False)[value_column]
    table = grouped.agg(["count", "mean", "median", "min", "max"]).reset_index()
    table = table.sort_values("count", ascending=False).head(30)
    for column in ("mean", "median", "min", "max"):
        table[column] = table[column].round(4)
    return {
        "operation": "compare_groups",
        "group_by": group_by,
        "value_column": value_column,
        "groups": to_jsonable(table.to_dict(orient="records")),
    }


def _aggregate(
    frame: pd.DataFrame,
    group_by: str,
    value_column: str,
    agg: AggName,
) -> dict[str, Any]:
    _ensure_columns(frame, [group_by, value_column])
    working = frame[[group_by, value_column]].copy()
    if agg != "count":
        working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    grouped = working.groupby(group_by, dropna=False)[value_column]
    series = getattr(grouped, agg)()
    table = series.reset_index(name=agg).sort_values(agg, ascending=False).head(30)
    return {
        "operation": "aggregate",
        "agg": agg,
        "groups": to_jsonable(table.to_dict(orient="records")),
    }


def _time_series(frame: pd.DataFrame, date_column: str, value_column: str, freq: str) -> dict[str, Any]:
    _ensure_columns(frame, [date_column, value_column])
    working = frame[[date_column, value_column]].copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    working = working.dropna()
    if working.empty:
        raise ValueError("Aucune date ou valeur exploitable pour la série.")
    indexed = working.set_index(date_column).sort_index()
    series = _resample(indexed[value_column], freq).dropna()
    records = [
        {"period": timestamp.date().isoformat(), "mean": round(float(value), 4)}
        for timestamp, value in series.items()
    ]
    return {
        "operation": "time_series",
        "freq": freq,
        "points": records[:60],
        "point_count": len(records),
    }


def _resample(series: pd.Series, freq: str) -> pd.Series:
    """`ME` est le code mensuel récent ; `M` reste accepté sur pandas plus ancien."""
    try:
        return series.resample(freq).mean()
    except ValueError:
        fallback = {"ME": "M", "M": "ME"}.get(freq, freq)
        return series.resample(fallback).mean()


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    _ensure_columns(frame, [column])
    return pd.to_numeric(frame[column], errors="coerce")


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(
            f"Colonnes absentes : {', '.join(missing)}. Colonnes reçues : {list(frame.columns)}"
        )


def _require(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"Paramètre requis pour cette opération : {name}.")
    return value
