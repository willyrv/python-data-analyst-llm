"""Recherche d'avis clients par SQL.

Les commentaires Olist sont en portugais. L'outil renvoie le texte original.
Une recherche vectorielle pourra remplacer `build_review_query` plus tard
sans changer le contrat vu par l'agent : filtres en entrée, extraits en sortie.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.config import Settings, get_settings
from src.tools.sql import execute_parameterized

_MAX_KEYWORDS = 5
_COMMENT_CHARS = 500


class ReviewArgs(BaseModel):
    only_late: bool = False
    max_score: int | None = Field(default=None, ge=1, le=5)
    keywords: list[str] = Field(default_factory=list)
    limit: int = Field(default=15, ge=1, le=30)

    @model_validator(mode="before")
    @classmethod
    def coerce_keywords(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("keywords"), str):
            data["keywords"] = [data["keywords"]]
        return data


def search_reviews(arguments: dict, settings: Settings | None = None) -> dict[str, Any]:
    args = ReviewArgs.model_validate(arguments or {})
    args.keywords = [word for word in (_clean_keyword(item) for item in args.keywords) if word]
    if not args.only_late and args.max_score is None and not args.keywords:
        raise ValueError(
            "Ajoute un filtre : only_late, max_score ou keywords. "
            "Un appel sans filtre renverrait des avis sans rapport avec la question."
        )
    sql, params = build_review_query(args)
    settings = settings or get_settings()
    result = execute_parameterized(sql, params, max_rows=args.limit, settings=settings)
    reviews = []
    for row in result.rows:
        comment = row.get("review_comment_message") or ""
        reviews.append(
            {
                "review_score": row.get("review_score"),
                "title": row.get("review_comment_title"),
                "comment": str(comment)[:_COMMENT_CHARS],
                "delay_days": row.get("delay_days"),
                "order_id": row.get("order_id"),
            }
        )
    return {
        "sql": sql,
        "filters": {
            "only_late": args.only_late,
            "max_score": args.max_score,
            "keywords": args.keywords,
        },
        "review_count": len(reviews),
        "reviews": reviews,
        "note": "Textes originaux en portugais. Ne cite que ces extraits.",
    }


def build_review_query(args: ReviewArgs) -> tuple[str, dict[str, Any]]:
    """Construit un SELECT paramétré. Le modèle ne choisit pas le SQL."""
    where = [
        "r.review_comment_message IS NOT NULL",
        "length(trim(r.review_comment_message)) > 0",
    ]
    params: dict[str, Any] = {"limit": args.limit}
    if args.only_late:
        where.append("o.order_delivered_customer_date > o.order_estimated_delivery_date")
    if args.max_score is not None:
        where.append("r.review_score <= :max_score")
        params["max_score"] = args.max_score
    keywords = [_clean_keyword(word) for word in args.keywords if _clean_keyword(word)]
    if len(keywords) > _MAX_KEYWORDS:
        raise ValueError(f"Maximum {_MAX_KEYWORDS} mots-clés.")
    if keywords:
        clauses = []
        for index, word in enumerate(keywords):
            key = f"kw{index}"
            params[key] = f"%{word}%"
            clauses.append(
                f"(r.review_comment_message ILIKE :{key} OR r.review_comment_title ILIKE :{key})"
            )
        where.append("(" + " OR ".join(clauses) + ")")
    sql = f"""
        SELECT
            r.review_score,
            r.review_comment_title,
            r.review_comment_message,
            r.order_id,
            ROUND(
                EXTRACT(EPOCH FROM (
                    o.order_delivered_customer_date - o.order_estimated_delivery_date
                )) / 86400.0,
                1
            ) AS delay_days
        FROM reviews AS r
        JOIN orders AS o ON o.order_id = r.order_id
        WHERE {" AND ".join(where)}
        ORDER BY r.review_score ASC, delay_days DESC NULLS LAST
        LIMIT :limit
    """
    return sql, params


def _clean_keyword(word: str) -> str:
    cleaned = " ".join(str(word).split())
    if not cleaned or len(cleaned) > 40:
        return ""
    # Les jokers LIKE restent des caractères littéraux : on les retire.
    return cleaned.replace("%", "").replace("_", "").replace("\\", "")
