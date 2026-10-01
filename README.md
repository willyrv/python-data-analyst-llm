# Small Models, Big Data

Démonstration pour **Mêlée Tech 2026** : un LLM open source, servi en local, devient une interface d'analyse sur le dataset e-commerce Olist.

Le modèle choisit des outils. Il ne répond pas à la place des données.

```text
LLM proposes an action
        ↓
Application validates it
        ↓
Tool executes it
```

**LLM + données + outils > LLM seul.** Si aucun outil n'est appelé, l'interface l'affiche clairement.

## Stack

| Couche | Composant |
| --- | --- |
| Interface | Streamlit |
| Agent | Python 3.11+, boucle écrite dans `src/agent.py` |
| Contrat LLM | SDK OpenAI, `tools` + `tool_choice="auto"` |
| Serveur de modèle | Ollama, vLLM, Torus Open WebUI, OpenAI ou Gemini |
| Données | PostgreSQL 16, Docker Compose, SQLAlchemy 2, psycopg |
| Analyse | pandas, matplotlib (backend Agg) |
| Validation | Pydantic |
| Tests | pytest |

Postgres est le seul service du `docker-compose.yml`. Le modèle tourne à part.

## Architecture

```text
Utilisateur
    │
    ▼
Streamlit (app.py)
    │  une question, sans historique précédent
    ▼
src/agent.py
    │  messages + schémas d'outils
    ▼
API compatible OpenAI
    │  tool_calls, ou JSON de repli
    ▼
src/parsing.py  →  src/tools/registry.py
    │                  valide, puis exécute
    ├─ query_database / schéma  → PostgreSQL (rôle olist_ro)
    ├─ analyze_dataframe        → pandas
    ├─ create_chart             → matplotlib
    └─ search_reviews           → SQL écrit par l'application
    │
    ▼
résultat d'outil renvoyé au modèle, puis réponse finale
```

La boucle est dans `src/agent.py`. Elle est volontairement courte : au plus N allers-retours, puis une réponse finale. Il n'y a pas de framework agentique. Le détail du mécanisme d'outils est dans [docs/agent.md](docs/agent.md).

| Outil | Rôle |
| --- | --- |
| `inspect_database_schema` | Liste des tables, ou colonnes d'une seule table |
| `query_database` | Un `SELECT` ou `WITH … SELECT`, plafonné en lignes |
| `analyze_dataframe` | Statistiques pandas sur un `SELECT` (pas de `exec`) |
| `create_chart` | bar, line, histogram, scatter, boxplot |
| `search_reviews` | Avis filtrés par SQL. Point d'extension si vous ajoutez une recherche vectorielle plus tard |

La synthèse est la dernière réponse du modèle, écrite seulement à partir des résultats d'outils.

## Installation

Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Les valeurs de `.env.example` correspondent au `docker-compose.yml` local. Les mots de passe sont ceux d'une démo sur une machine de conférence, pas ceux d'un serveur exposé.

## PostgreSQL

```bash
docker compose up -d postgres
```

Attendez que le healthcheck passe :

```bash
docker compose ps
```

## Dataset Olist

**Brazilian E-Commerce Public Dataset by Olist** :

<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>

Le jeton API (une ligne, généré sur la page Kaggle des jetons) se place dans `.secrets/kaggle_api_token`. Ce dossier est ignoré par git et n'est lisible que par le propriétaire. Le script ne contient pas le jeton.

```bash
python scripts/download_olist.py
```

Les CSV arrivent dans `data/olist/`. Le dossier doit contenir au minimum :

- `olist_customers_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `product_category_name_translation.csv`

```bash
python scripts/load_olist.py data/olist
```

La géolocalisation n'est pas nécessaire pour les trois questions de démo. Pour la charger quand même :

```bash
python scripts/load_olist.py data/olist --with-geolocation
```

Le chargement recrée les tables, puis accorde le `SELECT` au rôle lecture seule. Vous pouvez rejouer cette étape à l'écran :

```bash
python scripts/create_readonly_user.py
```

L'application utilise `DATABASE_URL` (rôle `olist_ro`). Les scripts de chargement utilisent `DATABASE_ADMIN_URL` (rôle `olist`). Le modèle ne voit ni l'une ni l'autre.

## LLM

N'importe quel serveur **compatible OpenAI** convient. Le modèle doit accepter les tool calls. Aucun modèle n'est imposé. La barre latérale permet de changer l'adresse, de lister les modèles et d'en choisir un, sans redémarrer l'application. La clé API reste dans la session du navigateur.

| Fournisseur | Adresse |
| --- | --- |
| Torus (Open WebUI) | `https://gentl.torus.ai/api` |
| OpenAI | `https://api.openai.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| vLLM local | `http://localhost:8000/v1` |
| Ollama | `http://localhost:11434/v1` |

Pour Torus, la clé se crée dans [gentl.torus.ai](https://gentl.torus.ai) → Settings → Account → API Keys. Au démarrage, l'application lit `.secrets/llm-api-keys.env` (`TORUS_API_KEY`, `OPENAI_CLOUD_API_KEY`, `GEMINI_API_KEY`) et préremplit la clé de chaque fournisseur. `OPENAI_API_KEY` dans `.env` reste celle du serveur de départ, par exemple Ollama. Ces variables sont facultatives.

Exemple vLLM. Le `--tool-call-parser` dépend de la famille du modèle (`hermes`, `llama3_json`, `mistral`, …) :

```bash
vllm serve MODEL_NAME \
    --host 0.0.0.0 \
    --port 8000 \
    --enable-auto-tool-choice \
    --tool-call-parser hermes
```

Puis dans `.env` :

```text
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=dummy
MODEL_NAME=MODEL_NAME
```

Avec Ollama, l'URL est en général `http://localhost:11434/v1`. Choisissez un modèle dont le template sait émettre des tool calls (Qwen2.5, Llama 3.1, Mistral, …).

Vérification rapide :

```bash
curl "$OPENAI_BASE_URL/models"
```

Si le modèle écrit le tool call en JSON dans le texte au lieu du champ `tool_calls`, l'application exécute quand même cet appel, puis le valide comme les autres. Ce repli est dans `src/parsing.py`.

## Application

```bash
streamlit run app.py
```

La barre latérale montre le modèle, l'URL du serveur, l'état de PostgreSQL, la température et le nombre maximum de tours. Trois boutons remplissent les questions de démo. **Reset conversation** efface l'historique affiché. Chaque question est envoyée seule au modèle : l'historique reste à l'écran, il n'est pas réinjecté dans le contexte.

`DEBUG=true`, ou le bouton **Mode debug**, affiche la requête envoyée au LLM, les tool calls, le SQL, la durée et les tokens lorsqu'ils sont disponibles. Le journal console est écrit dans le terminal qui lance Streamlit.

## Questions de démo

1. **SQL** — cinq catégories au plus gros chiffre d'affaires.
2. **Statistiques + graphique** — association entre retard de livraison et note, sans conclusion causale.
3. **SQL + texte** — raisons d'insatisfaction des commandes en retard, à partir des avis.

Les avis Olist sont en **portugais**. La synthèse est dans la langue de la question. Les citations restent des extraits renvoyés par l'outil.

## Benchmark

```bash
python scripts/benchmark.py
```

Les questions sont dans `data/evaluation_questions.json`. Le script mesure le temps, le nombre d'appels LLM, le nombre de tool calls, le modèle, et un succès simple : pas d'erreur, outil attendu réellement appelé, faits attendus présents s'il y en a. Le détail est écrit dans `outputs/benchmark_last.json`.

## Tests

```bash
pytest
```

Ils couvrent le refus de `DROP`, `DELETE`, `UPDATE`, les `SELECT` / `WITH` autorisés, les opérations pandas, les graphiques et le parsing des tool calls. PostgreSQL n'est pas requis pour `pytest`.

## Sécurité

Deux barrières indépendantes :

1. `src/tools/sql_safety.py` n'accepte qu'une instruction `SELECT` ou `WITH … SELECT`. `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE` et quelques fonctions (`pg_read_file`, `pg_sleep`, `dblink`, …) sont refusés avant toute connexion. Une requête refusée n'ouvre pas la base.
2. La session de l'application est ouverte avec `default_transaction_read_only=on` et un `statement_timeout`. Le rôle `olist_ro` n'a que `SELECT`.

Le SQL des avis et du schéma est écrit par l'application, avec des paramètres liés. Le modèle ne reçoit pas de shell, pas de chemin de fichier, pas d'identifiants.

Les résultats SQL renvoyés au modèle sont tronqués. Les agrégations doivent être faites dans le `SELECT`, pas dans la fenêtre de contexte.

## Hypothèses

Choix simples, assumés pour une démo :

- Le chiffre d'affaires est `SUM(order_items.price)`, hors `freight_value`. `payment_value` n'est pas utilisé : il mélange souvent le port et peut dupliquer des commandes.
- Une commande est en retard quand `order_delivered_customer_date` est postérieure à `order_estimated_delivery_date`.
- `analyze_dataframe` et `create_chart` ré-exécutent un `SELECT` validé. Il n'y a pas d'état caché entre les outils.
- Pas de RAG. `search_reviews` filtre en SQL. Pour une recherche vectorielle plus tard, remplacez le corps de cet outil : l'agent continue de recevoir des avis, pas une nouvelle architecture.
- La géolocalisation est optionnelle.
- La causalité n'est pas déductible de ces agrégats. Le prompt l'interdit, et la démo 2 doit parler d'association ou de corrélation.

## Checklist avant la conférence

- Dataset téléchargé et importé, sans réseau le jour J.
- `docker compose ps` : Postgres healthy.
- Sidebar Streamlit : rôle `olist_ro`, pas `olist`.
- `curl` sur `/v1/models` répond, tool calling activé côté serveur.
- Les trois boutons de démo ont été joués au moins une fois, température à 0,1.
- `DEBUG` désactivé sur l'écran projeté. Le terminal reste visible en secours, il reçoit le journal.
- Zoom navigateur suffisant pour la salle.
- Prévoir la phrase : les avis sont en portugais, les chiffres viennent des outils, une corrélation n'est pas une cause.
- Si le GPU ne répond plus : le validateur SQL, le schéma des outils et un `outputs/benchmark_last.json` d'une répétition suffisent à continuer l'explication.

## Structure

```text
app.py
src/agent.py            boucle LLM → validation → outil
docs/agent.md           comment le modèle découvre et appelle les outils
src/llm.py              client OpenAI vers le serveur local
src/parsing.py          tool calls natifs, repli JSON, masquage du raisonnement
src/tools/sql_safety.py barrière SQL
src/tools/sql.py        exécution plafonnée
src/tools/analysis.py   pandas, sans exec
src/tools/charts.py     matplotlib
src/tools/reviews.py    avis, extension possible
src/tools/schema.py     schéma à la demande
src/prompts/system_prompt.py
scripts/download_olist.py
scripts/load_olist.py
scripts/create_readonly_user.py
scripts/benchmark.py
```
