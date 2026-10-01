"""Charge les CSV Olist dans PostgreSQL.

Le téléchargement n'est pas fait ici. Voir le README.
Usage : python scripts/load_olist.py /chemin/vers/olist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from sqlalchemy import text

from src.config import get_settings
from src.database import admin_engine
from src.readonly import grant_readonly

# Nom de table -> fichier public Olist, colonnes de dates, index.
TABLES: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("customers", "olist_customers_dataset.csv", (), ("customer_id",)),
    (
        "orders",
        "olist_orders_dataset.csv",
        (
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
        ("order_id", "customer_id"),
    ),
    (
        "order_items",
        "olist_order_items_dataset.csv",
        ("shipping_limit_date",),
        ("order_id", "product_id", "seller_id"),
    ),
    ("products", "olist_products_dataset.csv", (), ("product_id", "product_category_name")),
    ("sellers", "olist_sellers_dataset.csv", (), ("seller_id",)),
    ("payments", "olist_order_payments_dataset.csv", (), ("order_id",)),
    (
        "reviews",
        "olist_order_reviews_dataset.csv",
        ("review_creation_date", "review_answer_timestamp"),
        ("order_id",),
    ),
    (
        "product_categories",
        "product_category_name_translation.csv",
        (),
        ("product_category_name",),
    ),
]

GEOLOCATION = (
    "geolocation",
    "olist_geolocation_dataset.csv",
    (),
    ("geolocation_zip_code_prefix",),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe le dataset Olist dans PostgreSQL.")
    parser.add_argument("dataset_dir", type=Path, help="Dossier qui contient les CSV Olist")
    parser.add_argument(
        "--with-geolocation",
        action="store_true",
        help="Charge aussi olist_geolocation_dataset.csv (volumineux, inutile pour les 3 démos).",
    )
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.expanduser().resolve()
    tables = list(TABLES)
    if args.with_geolocation:
        tables.append(GEOLOCATION)

    missing = [filename for _, filename, _, _ in tables if not (dataset_dir / filename).exists()]
    if missing:
        print(f"Dossier : {dataset_dir}")
        print("Fichiers manquants :")
        for name in missing:
            print(f"  - {name}")
        print("Téléchargez le dataset Olist (voir README) et passez le dossier des CSV.")
        sys.exit(1)

    settings = get_settings()
    engine = admin_engine(settings)
    for table, filename, dates, indexes in tables:
        path = dataset_dir / filename
        print(f"[LOAD] {filename} -> {table}")
        frame = pd.read_csv(path, parse_dates=list(dates) if dates else None)
        with engine.begin() as conn:
            frame.to_sql(table, conn, if_exists="replace", index=False, chunksize=5_000)
            for column in indexes:
                index_name = f"idx_{table}_{column}"
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        print(f"[LOAD] {table}: {count} lignes")

    with engine.begin() as conn:
        conn.execute(text("ANALYZE"))
    user = grant_readonly(settings)
    print(f"[LOAD] Terminé. Rôle {user} : SELECT uniquement.")
    print("       Vous pouvez relancer python scripts/create_readonly_user.py pour montrer cette étape.")


if __name__ == "__main__":
    main()
