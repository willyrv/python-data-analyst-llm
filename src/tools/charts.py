"""Graphiques matplotlib standards, enregistrés en PNG pour Streamlit."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import pandas as pd
from pydantic import BaseModel, Field

from src.config import Settings, get_settings
from src.tools.sql import execute_select, result_to_frame

ChartType = Literal["bar", "line", "histogram", "scatter", "boxplot"]
_CHART_ROW_LIMIT = 20_000


class ChartArgs(BaseModel):
    sql: str
    chart_type: ChartType
    x: str
    y: str | None = None
    title: str = ""


def create_chart(arguments: dict, settings: Settings | None = None) -> dict:
    args = ChartArgs.model_validate(arguments)
    settings = settings or get_settings()
    result = execute_select(args.sql, max_rows=_CHART_ROW_LIMIT, settings=settings)
    frame = result_to_frame(result)
    path = render_chart(frame, args, settings.chart_dir)
    return {
        "chart_path": str(path),
        "chart_type": args.chart_type,
        "rows": int(len(frame)),
        "truncated": result.truncated,
        "sql": result.sql,
        "title": args.title,
    }


def render_chart(frame: pd.DataFrame, args: ChartArgs, directory: Path) -> Path:
    """Dessine un PNG. Testable sans PostgreSQL."""
    if frame.empty:
        raise ValueError("Aucune donnée à représenter.")
    if args.x not in frame.columns:
        raise ValueError(f"Colonne x absente : {args.x}. Colonnes : {list(frame.columns)}")
    if args.chart_type != "histogram" and not args.y:
        raise ValueError("Le paramètre y est requis pour ce type de graphique.")
    if args.y and args.y not in frame.columns:
        raise ValueError(f"Colonne y absente : {args.y}. Colonnes : {list(frame.columns)}")

    directory.mkdir(parents=True, exist_ok=True)
    _prune(directory)
    destination = directory / f"chart-{uuid.uuid4().hex}.png"

    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    try:
        _draw(ax, frame, args)
        ax.set_title(args.title or _default_title(args), fontsize=16, pad=12)
        ax.tick_params(labelsize=11)
        fig.tight_layout()
        fig.savefig(destination, dpi=120)
    finally:
        plt.close(fig)
    return destination


def _draw(ax: plt.Axes, frame: pd.DataFrame, args: ChartArgs) -> None:
    if args.chart_type == "bar":
        data = frame[[args.x, args.y]].head(40)
        ax.bar(data[args.x].astype(str), pd.to_numeric(data[args.y], errors="coerce"), color="#1f4e79")
        ax.set_xlabel(args.x)
        ax.set_ylabel(args.y)
        ax.tick_params(axis="x", rotation=25)
        return
    if args.chart_type == "line":
        data = frame[[args.x, args.y]].copy()
        data[args.y] = pd.to_numeric(data[args.y], errors="coerce")
        ax.plot(data[args.x].astype(str), data[args.y], color="#1f4e79", linewidth=2)
        ax.set_xlabel(args.x)
        ax.set_ylabel(args.y)
        ax.tick_params(axis="x", rotation=25)
        return
    if args.chart_type == "histogram":
        series = pd.to_numeric(frame[args.x], errors="coerce").dropna()
        if series.empty:
            raise ValueError(f"Aucune valeur numérique dans {args.x}.")
        ax.hist(series.head(5000), bins=20, color="#1f4e79", edgecolor="white")
        ax.set_xlabel(args.x)
        ax.set_ylabel("effectif")
        return
    if args.chart_type == "scatter":
        data = frame[[args.x, args.y]].copy()
        data[args.x] = pd.to_numeric(data[args.x], errors="coerce")
        data[args.y] = pd.to_numeric(data[args.y], errors="coerce")
        data = data.dropna().head(5000)
        if data.empty:
            raise ValueError("Nuage de points impossible : x et y doivent être numériques.")
        ax.scatter(data[args.x], data[args.y], s=14, alpha=0.35, color="#1f4e79")
        ax.set_xlabel(args.x)
        ax.set_ylabel(args.y)
        return
    if args.chart_type == "boxplot":
        data = frame[[args.x, args.y]].copy()
        data[args.y] = pd.to_numeric(data[args.y], errors="coerce")
        data = data.dropna()
        if data.empty:
            raise ValueError("Boxplot impossible : aucune valeur numérique.")
        labels = list(dict.fromkeys(data[args.x].astype(str).tolist()))
        if len(labels) > 12:
            raise ValueError("Trop de catégories pour un boxplot (12 maximum). Agrège ou filtre.")
        groups = [data.loc[data[args.x].astype(str) == label, args.y].tolist() for label in labels]
        try:
            ax.boxplot(groups, tick_labels=labels)
        except TypeError:
            ax.boxplot(groups, labels=labels)
        ax.set_xlabel(args.x)
        ax.set_ylabel(args.y)
        return
    raise ValueError(f"Type de graphique inconnu : {args.chart_type}")


def _default_title(args: ChartArgs) -> str:
    if args.y:
        return f"{args.y} par {args.x}"
    return args.x


def _prune(directory: Path, keep: int = 30) -> None:
    files = sorted(directory.glob("chart-*.png"), key=lambda path: path.stat().st_mtime)
    for path in files[:-keep]:
        path.unlink(missing_ok=True)
