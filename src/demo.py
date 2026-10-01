"""Questions préconfigurées pour la démonstration sur scène."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoQuestion:
    button: str
    question: str
    expected_tool: str


DEMOS: tuple[DemoQuestion, ...] = (
    DemoQuestion(
        button="Demo 1 — Top product categories",
        question=(
            "Quelles sont les cinq catégories de produits ayant généré "
            "le plus de chiffre d'affaires ?"
        ),
        expected_tool="query_database",
    ),
    DemoQuestion(
        button="Demo 2 — Delivery delay vs satisfaction",
        question=(
            "Le retard de livraison a-t-il un impact mesurable sur la "
            "satisfaction des clients ? Montre-moi les données et génère "
            "un graphique."
        ),
        expected_tool="create_chart",
    ),
    DemoQuestion(
        button="Demo 3 — Why are delayed customers unhappy?",
        question=(
            "Quelles sont les principales raisons d'insatisfaction des "
            "clients dont la commande est arrivée en retard ? Appuie ta "
            "réponse sur les avis clients."
        ),
        expected_tool="search_reviews",
    ),
)
