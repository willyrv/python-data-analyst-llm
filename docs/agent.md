# Comment l'agent est construit

L'agent est une boucle écrite à la main dans `src/agent.py`. Elle n'utilise ni LangChain, ni LlamaIndex, ni CrewAI. Le modèle de langage propose une action. L'application la valide. Un outil Python l'exécute. Le résultat réel revient au modèle.

Le modèle n'est jamais la source de vérité. Un chiffre, un classement ou une citation n'est affiché comme un fait que s'il sort d'un outil.

## Une question, une boucle

`run_agent` repart de zéro à chaque question. L'historique visible dans Streamlit n'est pas renvoyé.

Le contexte initial tient en deux messages :

1. le prompt système (`src/prompts/system_prompt.py`) : rôle, règles métier Olist, noms des outils ;
2. la question de l'utilisateur.

Ensuite, pour au plus `max_tool_rounds` tours (6 par défaut) :

1. `complete()` envoie les messages, la température (0,1 par défaut) et la liste des outils ;
2. s'il n'y a pas d'appel d'outil, le texte de l'assistant est la réponse finale ;
3. sinon chaque appel est validé, exécuté, journalisé, puis ajouté à l'historique comme message `tool` ;
4. le tour suivant voit ce résultat et peut enchaîner un autre outil, ou conclure.

Au-delà de la limite, l'agent s'arrête avec un message explicite. Les étapes déjà exécutées restent affichées. Un contenu d'outil est tronqué à 12 000 caractères avant d'être renvoyé au modèle.

## Comment le modèle apprend quels outils existent

Le modèle ne lit pas le code Python. Il reçoit, à chaque appel, le paramètre `tools` de l'API Chat Completions, avec `tool_choice="auto"`.

`tool_schemas()` dans `src/tools/registry.py` produit cette liste. Chaque entrée est un objet JSON Schema :

```json
{
  "type": "function",
  "function": {
    "name": "query_database",
    "description": "Exécute un unique SELECT ou WITH ... SELECT en lecture seule.",
    "parameters": {
      "type": "object",
      "properties": {
        "sql": {"type": "string", "description": "Requête SELECT PostgreSQL."}
      },
      "required": ["sql"]
    }
  }
}
```

Cinq fonctions sont déclarées :

| Nom | Ce que le modèle est autorisé à demander |
| --- | --- |
| `inspect_database_schema` | La liste des tables, ou les colonnes d'une table |
| `query_database` | Un `SELECT` ou `WITH … SELECT` |
| `analyze_dataframe` | Une opération pandas parmi un enum fermé |
| `create_chart` | Un type de graphique, des colonnes `x` et `y` |
| `search_reviews` | Des filtres (`only_late`, `max_score`, `keywords`), pas du SQL |

La description et les paramètres sont le mode d'emploi. Le prompt système répète les mêmes noms et les règles métier (chiffre d'affaires hors fret, définition du retard, avis en portugais). Les deux sources se complètent : le schéma dit *comment appeler*, le prompt dit *quand* et *avec quelles conventions*.

`tool_choice="auto"` laisse le modèle décider. Il peut répondre en texte seul, ou émettre un ou plusieurs appels. Il ne peut pas inventer une fonction hors de cette liste et la faire exécuter : `dispatch` refuse un nom inconnu, et le repli JSON de `src/parsing.py` ignore un nom qui n'est pas dans `known_tool_names()`.

## Comment le modèle appelle un outil

Le chemin normal est le champ `tool_calls` de la réponse Chat Completions :

```json
{
  "id": "call_1",
  "type": "function",
  "function": {
    "name": "query_database",
    "arguments": "{\"sql\": \"SELECT ...\"}"
  }
}
```

`extract_tool_calls` lit ce champ. Les arguments sont une chaîne JSON. S'ils sont illisibles, l'appel n'est pas exécuté : le modèle reçoit l'erreur et peut réessayer dans la limite de tours.

Certains petits modèles écrivent l'appel dans le texte, souvent dans un bloc ` ```json `. Si `tool_calls` est vide, le parseur accepte un objet `{"tool", "arguments"}` ou `{"name", "arguments"}`, uniquement quand le nom est dans le registre. La validation qui suit est la même.

Les balises `<think>` sont retirées avant l'affichage et avant de réinjecter le message assistant. Elles ne deviennent pas le prochain prompt.

## Ce qui se passe après l'appel

`dispatch` est la seule porte d'exécution.

1. Le nom doit être dans `_HANDLERS`.
2. Les arguments passent par Pydantic (`QueryArgs` pour le SQL, modèles dédiés pour l'analyse, le graphique et les avis) ou par le validateur du schéma.
3. Pour le SQL, `validate_readonly_sql` refuse tout ce qui n'est pas un unique `SELECT` ou `WITH … SELECT`, avant d'ouvrir une connexion. La session PostgreSQL est en plus en lecture seule, avec un `statement_timeout`, sous le rôle `olist_ro`.
4. `analyze_dataframe` et `create_chart` choisissent une opération ou un type dans un enum. Il n'y a pas de `exec()` ni de code Python envoyé par le modèle.
5. `search_reviews` écrit lui-même le `SELECT`, avec des paramètres liés. Le modèle ne fournit que les filtres.

Le résultat revient dans un message :

```json
{
  "role": "tool",
  "tool_call_id": "call_1",
  "content": "5 lignes renvoyées.\n..."
}
```

Le modèle ne reçoit pas les 200 lignes maximales du SQL : l'aperçu fait 20 lignes. Les statistiques pandas et les graphiques renvoient un résumé, pas le tableau brut. Le graphique PNG est affiché par Streamlit ; le modèle est seulement informé qu'il existe.

Une erreur d'outil (SQL rejeté, colonne inconnue, outil inconnu) est aussi un message `tool`. Le modèle peut corriger sa proposition au tour suivant. Ce n'est pas une exception qui arrête l'application.

## Gemini et la thought signature

Les modèles Gemini 3, via l'API compatible OpenAI, joignent une `thought_signature` au premier appel d'outil, dans `extra_content.google`. Le tour suivant doit renvoyer cette signature avec l'appel. `assistant_payload` la conserve. Sans elle, Gemini répond 400 et la boucle s'arrête avant la synthèse, même si l'outil a déjà tourné.

Les autres serveurs n'envoient pas ce champ. Le message assistant reste alors limité à l'identifiant, au nom et aux arguments.

## Ce que la boucle ne fait pas

- Elle ne donne pas au modèle les identifiants PostgreSQL, un shell, ni le système de fichiers.
- Elle ne réinjecte pas les questions précédentes.
- Elle ne laisse pas le modèle choisir le code Python exécuté.
- Elle ne traite pas la dernière phrase du modèle comme un outil de plus : c'est la réponse, produite seulement après les résultats qu'il a réellement reçus.
