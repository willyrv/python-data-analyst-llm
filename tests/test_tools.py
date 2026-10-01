"""Outils analytiques, graphiques et avis, sans base et sans LLM."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.demo import DEMOS
from src.tools.analysis import AnalysisArgs, run_operation
from src.tools.charts import ChartArgs, render_chart
from src.tools.reviews import ReviewArgs, build_review_query, search_reviews
from src.tools.sql import QueryResult, format_table


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "delivery_status": ["à l'heure", "à l'heure", "en retard", "en retard"],
            "review_score": [5, 4, 2, 1],
            "delay_days": [-1, 0, 3, 8],
            "day": pd.to_datetime(["2018-01-01", "2018-01-08", "2018-01-15", "2018-02-01"]),
        }
    )


def test_compare_groups_returns_means():
    summary = run_operation(
        _frame(),
        AnalysisArgs(sql="select 1", operation="compare_groups", group_by="delivery_status", value_column="review_score"),
    )
    groups = {row["delivery_status"]: row["mean"] for row in summary["groups"]}
    assert groups["à l'heure"] == 4.5
    assert groups["en retard"] == 1.5


def test_correlation_is_numeric_and_not_a_causal_claim():
    summary = run_operation(
        _frame(),
        AnalysisArgs(sql="select 1", operation="correlation", columns=["delay_days", "review_score"]),
    )
    assert "correlation" in summary
    assert summary["operation"] == "correlation"
    dumped = json.dumps(summary)
    assert "caus" not in dumped


def test_quantiles_and_time_series():
    quantiles = run_operation(_frame(), AnalysisArgs(sql="select 1", operation="quantiles", column="delay_days"))
    assert quantiles["quantiles"]["0.5"] == 1.5
    series = run_operation(
        _frame(),
        AnalysisArgs(
            sql="select 1",
            operation="time_series",
            date_column="day",
            value_column="review_score",
            freq="ME",
        ),
    )
    assert series["point_count"] >= 1


def test_missing_column_is_explicit():
    with pytest.raises(ValueError, match="absentes"):
        run_operation(_frame(), AnalysisArgs(sql="select 1", operation="quantiles", column="nope"))


def test_render_bar_chart_writes_a_png(tmp_path: Path):
    path = render_chart(
        pd.DataFrame({"category": ["a", "b"], "revenue": [10, 30]}),
        ChartArgs(sql="select 1", chart_type="bar", x="category", y="revenue", title="CA"),
        tmp_path,
    )
    assert path.exists()
    assert path.stat().st_size > 0


def test_histogram_does_not_require_y(tmp_path: Path):
    path = render_chart(
        _frame(),
        ChartArgs(sql="select 1", chart_type="histogram", x="review_score", title="Notes"),
        tmp_path,
    )
    assert path.exists()


def test_review_query_is_parameterized_and_filters_late_orders():
    sql, params = build_review_query(ReviewArgs(only_late=True, max_score=2, keywords=["atraso"], limit=10))
    assert "order_delivered_customer_date > o.order_estimated_delivery_date" in sql
    assert ":max_score" in sql
    assert ":kw0" in sql
    assert params["max_score"] == 2
    assert params["kw0"] == "%atraso%"
    assert "atraso" not in sql


def test_review_search_requires_a_filter():
    with pytest.raises(ValueError):
        search_reviews({})


def test_like_wildcards_in_keywords_are_not_passed_through():
    sql, params = build_review_query(ReviewArgs(keywords=["100%"], max_score=3))
    assert params["kw0"] == "%100%"
    assert "100%" not in sql


def test_format_table_marks_truncation():
    result = QueryResult(
        columns=["category", "revenue"],
        rows=[{"category": "bed_bath_table", "revenue": 12.5}],
        row_count=1,
        truncated=True,
        sql="SELECT 1",
    )
    text = format_table(result)
    assert "bed_bath_table" in text
    assert "tronqué" in text


def test_benchmark_file_contains_the_three_demo_questions():
    payload = json.loads(Path("data/evaluation_questions.json").read_text(encoding="utf-8"))
    questions = {item["question"] for item in payload}
    for demo in DEMOS:
        assert demo.question in questions
        match = next(item for item in payload if item["question"] == demo.question)
        assert match["expected_tool"] == demo.expected_tool
