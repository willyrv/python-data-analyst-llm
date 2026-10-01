"""Crée un rôle PostgreSQL qui ne peut que lire les tables Olist.

À lancer après le chargement, avec DATABASE_ADMIN_URL.
Le chargement rappelle aussi cette opération, car DROP/CREATE des tables
annule les GRANT précédents.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.readonly import grant_readonly


def main() -> None:
    user = grant_readonly()
    print(f"Rôle {user} prêt : SELECT uniquement.")
    print("L'application doit utiliser DATABASE_URL avec ce rôle, pas le rôle propriétaire.")


if __name__ == "__main__":
    main()
