# Small Models, Big Data : construire un Data Analyst avec un LLM auto-hébergé

**Intervenant : Willy Rodriguez, chercheur IA chez Torus Actions**  
**Format : 20 minutes de présentation, puis 10 minutes de démonstration**  
**Public : professionnels techniques, développeurs et praticiens de la donnée**

## Mode d’emploi

Les sections « À afficher » constituent le texte des slides. Les notes orales développent le propos sans surcharger l’écran. Les suggestions visuelles indiquent les éléments à préparer pour le futur diaporama.

Le fil conducteur est une enquête sur les ventes d’un e-commerce fictif. Le scénario associe une base PostgreSQL, des outils Python et des documents commerciaux. Les exemples de schéma et de requêtes proposés ici sont pédagogiques et devront correspondre au jeu de données de la démo. Aucun résultat expérimental n’est présumé. La slide 7 comporte un tableau à compléter après les essais.

**Message central : le LLM orchestre l’analyse. Les données et les outils produisent les résultats que l’on peut vérifier.**

## Déroulé général

| Slide | Sujet | Créneau | Durée |
| --- | --- | --- | --- |
| 1 | La question métier | 0–2 min | 2 min |
| 2 | Les besoins d’un assistant d’analyse | 2–4 min | 2 min |
| 3 | L’auto-hébergement | 4–6 min | 2 min |
| 4 | L’architecture et le cycle d’exécution | 6–9 min | 3 min |
| 5 | SQL et les faits | 9–11 min | 2 min |
| 6 | Python et le contexte documentaire | 11–13 min | 2 min |
| 7 | La comparaison des modèles | 13–16 min | 3 min |
| 8 | La fiabilité et les limites | 16–18 min | 2 min |
| 9 | Le scénario de démonstration | 18–20 min | 2 min |
| Démo | Une enquête en trois étapes | 20–30 min | 10 min |

---

## Slide 1 — Une question métier comme point de départ

**Durée : 2 minutes, de 0:00 à 2:00**

### À afficher

# Small Models, Big Data

**Construire un Data Analyst avec un LLM auto-hébergé**

> « Notre chiffre d’affaires baisse : quels produits sont concernés, et pourquoi ? »

Willy Rodriguez — Torus Actions

### Notes orales

« Je suis chercheur IA chez Torus Actions, avec un parcours en mathématiques appliquées et en analyse de données. Aujourd’hui, nous allons examiner comment construire un assistant capable de répondre à une question d’analyse en utilisant un modèle de langage hébergé sur notre propre machine.

Prenons une situation concrète. Une entreprise constate une baisse de son chiffre d’affaires. Elle souhaite savoir quels produits contribuent à cette baisse et si ses rapports commerciaux apportent des éléments d’explication.

Pour répondre, il faut interroger les ventes, comparer des périodes, calculer les contributions des produits et consulter des documents. L’assistant devra donc choisir des outils et exploiter leurs résultats.

Nous allons construire mentalement ce système, puis le regarder fonctionner. La question qui nous intéresse est la suivante : quel niveau de service pouvons-nous obtenir avec un modèle relativement petit, lorsque nous lui donnons les bons outils ?

Pendant la démo, nous regarderons aussi la requête, le graphique et les sources. Ce sont ces éléments qui nous permettront d’évaluer la réponse. »

### Suggestion visuelle

Une slide de titre sobre avec la question métier en grand. Aucun chiffre de baisse avant d’avoir interrogé le dataset.

### Transition

« Commençons par les informations et les capacités nécessaires pour répondre à cette question. »

---

## Slide 2 — Les besoins d’un assistant d’analyse

**Durée : 2 minutes, de 2:00 à 4:00**

### À afficher

**Pour répondre à une question sur l’entreprise, l’assistant doit disposer de :**

- Données accessibles et définitions métier explicites.
- Outils de requête et de calcul.
- Documents pour retrouver le contexte.
- Traces permettant de vérifier la réponse.

**Une réponse plausible peut contenir un chiffre faux.**

### Notes orales

« Un modèle de langage peut proposer une démarche pertinente. Il peut suggérer de comparer les ventes par mois, de regarder les produits ou de rechercher une rupture de stock. En revanche, il a besoin d’un accès effectif aux ventes de l’entreprise pour calculer les résultats.

Il lui faut aussi une définition de ce que nous cherchons. Le chiffre d’affaires inclut-il les taxes ? Les commandes annulées ? Les remboursements ? Comparons-nous deux mois complets ? Ces choix modifient la réponse, même lorsque la requête s’exécute correctement.

Nous allons donc fournir au modèle un environnement d’analyse : le schéma de la base, des définitions métier et des outils aux fonctions précises. Il pourra demander une extraction SQL, utiliser Python pour un graphique et consulter les documents disponibles.

Enfin, une réponse fluide ne suffit pas pour vérifier une analyse. Nous voulons pouvoir retrouver la période utilisée, la méthode de calcul et les sources. C’est pourquoi l’interface montrera les étapes utiles à cette vérification.

Le rôle du modèle sera de comprendre la demande, de choisir les opérations et de restituer les résultats avec leurs limites. »

### Suggestion visuelle

Un tableau de deux colonnes : « Besoin » et « Élément fourni au système », avec les quatre besoins de la slide.

### Transition

« Ce fonctionnement peut s’appuyer sur un modèle auto-hébergé. Voyons ce que ce choix implique. »

---

## Slide 3 — L’auto-hébergement et ses compromis

**Durée : 2 minutes, de 4:00 à 6:00**

### À afficher

**Environnement de la démonstration**

- Ollama pour servir le modèle.
- GPU NVIDIA RTX 4090 sur la machine d’inférence.
- Application cliente sur le réseau local.

| Intérêt recherché | Contrainte à prendre en compte |
| --- | --- |
| Maîtrise du lieu de traitement | Sécurisation des accès et des journaux |
| Choix du modèle et de sa configuration | Mémoire GPU et taille du contexte |
| Maîtrise de l’infrastructure | Installation, maintenance et suivi |

### Notes orales

« Pour cette démonstration, Ollama sert le modèle sur une machine équipée d’une RTX 4090. L’application peut tourner sur une autre machine du réseau local et lui envoyer les demandes d’inférence.

L’intérêt de cette organisation est de maîtriser l’environnement dans lequel nous traitons les données et de choisir notre modèle. Pour qu’un traitement reste local, il faut aussi que les autres composants, notamment les embeddings et la recherche documentaire, utilisent des services locaux.

L’auto-hébergement demande en contrepartie de gérer les ressources et l’exploitation. Il faut installer les composants, sécuriser l’accès au service et surveiller son fonctionnement. Une application locale conserve également des données dans ses journaux ou ses fichiers temporaires. Le lieu d’hébergement ne règle donc pas, à lui seul, toutes les questions de confidentialité.

Pour le modèle, nous devons considérer sa taille, sa quantification et le contexte que nous lui envoyons. Nous mesurerons leur effet sur la mémoire et la latence dans notre configuration.

Le choix se fait finalement à partir des tâches : comprendre le schéma, produire une requête correcte, appeler les outils et utiliser les résultats. C’est sur ces capacités que nous comparerons les modèles. »

### Suggestion visuelle

Un schéma simple des deux machines reliées par le réseau local, avec leurs composants nommés. Éviter les détails Docker à ce stade.

### Transition

« Voici maintenant les composants qui transforment ce service de modèle en assistant d’analyse. »

---

## Slide 4 — L’architecture du Data Analyst

**Durée : 3 minutes, de 6:00 à 9:00**

### À afficher

| Composant | Fonction |
| --- | --- |
| Interface | Recevoir la question et montrer les résultats |
| LLM local | Interpréter la demande et proposer un appel d’outil |
| Orchestrateur | Contrôler les appels et gérer le cycle d’exécution |
| PostgreSQL | Interroger les données structurées |
| Python isolé | Calculer et produire des graphiques |
| Recherche documentaire | Retrouver des passages utiles et leurs sources |

**Cycle : demande, choix d’un outil, contrôle, exécution, résultat, synthèse.**

### Notes orales

« L’interface reçoit une question en langage naturel. L’application transmet au modèle la demande, les informations nécessaires et la description des outils disponibles.

Le modèle peut alors proposer un appel d’outil. Par exemple, pour connaître le chiffre d’affaires mensuel, il propose une requête SQL. L’orchestrateur reçoit cette proposition, la contrôle et décide si elle peut être exécutée dans le cadre autorisé.

La base calcule le résultat. L’application renvoie ce résultat au modèle, qui peut produire une réponse ou demander une étape supplémentaire. Dans notre exemple, il pourra ensuite demander une extraction par produit, puis un graphique.

Cette séparation est essentielle pour comprendre ce que nous appelons ici un assistant ou un agent. Le modèle propose les opérations. L’application gère l’exécution, les permissions et les limites. Les outils effectuent les traitements.

Nous pouvons prévoir un nombre maximal d’étapes et un arrêt lorsqu’il manque une information. Si la question “pourquoi les ventes baissent-elles ?” exige des données absentes, l’assistant doit signaler cette limite.

Pour les documents, la recherche retrouve des passages pertinents et les transmet au modèle avec leurs références. Cette étape apporte un contexte supplémentaire, mais elle ne transforme pas automatiquement une observation commerciale en preuve de causalité.

Dans la démo, nous rendrons visibles les appels d’outils et leurs sorties utiles. Le public pourra suivre comment l’assistant passe de la question au résultat. »

### Exemple d’appel à montrer

Exemple pédagogique d’un format interne possible. Ce format ne présume pas du contrat exact de l’application.

```json
{
  "tool": "query_sales",
  "arguments": {
    "period": "last_two_complete_months",
    "group_by": "month",
    "metric": "revenue"
  }
}
```

### Suggestion visuelle

Un schéma d’architecture avec l’orchestrateur au centre. Afficher ensuite un appel d’outil et sa sortie sur le même support, en remplaçant le schéma lors de l’explication.

### Transition

« Regardons d’abord la partie qui nous donne les faits chiffrés : l’interrogation SQL. »

---

## Slide 5 — SQL : retrouver les faits

**Durée : 2 minutes, de 9:00 à 11:00**

### À afficher

> « Quel est le chiffre d’affaires mensuel sur les derniers mois complets ? »

- Le modèle reçoit le schéma et les définitions métier.
- Il propose une requête que l’application contrôle.
- PostgreSQL exécute le calcul.
- La réponse indique la période, le périmètre et le résultat.

**Une requête valide peut appliquer une mauvaise définition métier.**

### Notes orales

« La première difficulté est de traduire la question en opérations sur les bonnes tables. Où se trouve la date ? Le prix enregistré est-il le prix réellement payé ? Une jointure risque-t-elle de compter deux fois une vente ?

Pour réduire ces ambiguïtés, nous pouvons exposer une vue métier dédiée, par exemple une vue des ventes avec le montant net de chaque ligne. Cela donne au modèle un schéma plus simple et permet de centraliser certaines règles de calcul.

Le résultat dépend néanmoins du périmètre choisi. Un mois en cours ne se compare pas directement à un mois complet. Les annulations et les remboursements doivent suivre une règle explicite. L’assistant doit annoncer ces choix ou demander une précision lorsque la question reste ambiguë.

La requête fournit une trace de la méthode. Nous pouvons vérifier les filtres, l’agrégation et les colonnes utilisées. Mais le fait qu’elle s’exécute sans erreur ne garantit pas qu’elle répond à la bonne question.

Pendant la démo, je montrerai donc le résultat avec la requête et la définition du chiffre d’affaires utilisée. »

### Exemple SQL pour les notes ou une capture

Hypothèse pédagogique : la vue `sales` contient une date `sale_date` et un montant de ligne `net_amount` conforme à la définition métier retenue. Les dates sont des paramètres de l’application.

```sql
SELECT
    date_trunc('month', sale_date)::date AS month,
    SUM(net_amount) AS revenue
FROM sales
WHERE sale_date >= :start_date
  AND sale_date < :end_date
GROUP BY 1
ORDER BY 1;
```

### Suggestion visuelle

Une capture lisible de la requête et de quelques lignes de résultat. Le code complet peut rester dans les notes si l’écran devient trop chargé.

### Transition

« Nous avons les chiffres. Python nous aide à les explorer, et les documents apportent des éléments de contexte. »

---

## Slide 6 — Python et les documents : approfondir l’analyse

**Durée : 2 minutes, de 11:00 à 13:00**

### À afficher

| Outil | Question traitée | Sortie vérifiable |
| --- | --- | --- |
| SQL | Quels produits contribuent à la baisse ? | Ventes par produit et par période |
| Python | Quelle est l’ampleur de leur contribution ? | Calculs et graphique |
| Recherche documentaire | Que disent les rapports sur ces produits ? | Passages cités et références |

**Les chiffres établissent la variation. Les documents alimentent les hypothèses d’explication.**

### Notes orales

« Pour identifier les produits concernés, nous comparons leur chiffre d’affaires sur deux périodes. Pour chaque produit, nous calculons une différence en euros. Nous pouvons ensuite trier les contributions et montrer celles qui expliquent comptablement le plus la baisse totale.

Cette distinction compte : un produit peut baisser fortement en pourcentage tout en représentant une faible part des ventes. Le graphique devra donc répondre précisément à la question posée.

Python reçoit les données extraites et produit le graphique. Nous conservons le lien entre les valeurs affichées et le tableau source. Les produits en croissance doivent aussi entrer dans le calcul global, car ils peuvent compenser une partie des baisses.

Ensuite, nous recherchons des documents qui mentionnent ces produits et la période étudiée. Cette approche s’appelle RAG, pour Retrieval-Augmented Generation, ou génération augmentée par la recherche. Elle fournit au modèle des passages à utiliser dans sa réponse.

Un rapport peut évoquer une rupture de stock ou une campagne terminée. Cela constitue une piste à examiner. L’assistant doit citer le document et distinguer cette piste de ce que les chiffres démontrent directement. »

### Suggestion visuelle

Un graphique de contributions à la variation du chiffre d’affaires, accompagné d’un court extrait documentaire sourcé. Utiliser les résultats réels du dataset préparé.

### Transition

« Nous pouvons maintenant évaluer les modèles sur ces tâches précises. »

---

## Slide 7 — Un petit modèle suffit-il ?

**Durée : 3 minutes, de 13:00 à 16:00**

### À afficher

**Comparaison sur les mêmes questions et les mêmes données**

| Modèle et quantification | Pic mémoire GPU | Latence de bout en bout | Réponses correctes / N |
| --- | --- | --- | --- |
| [Modèle A] | [À mesurer] | [À mesurer] | [À mesurer] |
| [Modèle B] | [À mesurer] | [À mesurer] | [À mesurer] |
| [Modèle C, si testé] | [À mesurer] | [À mesurer] | [À mesurer] |

**Critères : choix des outils, calculs corrects, utilisation des sources et gestion des informations manquantes.**

### Notes orales

« Pour choisir un modèle, nous devons mesurer son comportement dans l’application. Une réponse bien formulée peut cacher une mauvaise requête ou une conclusion qui dépasse les données.

Je propose un petit ensemble fixe de questions. Certaines demandent un chiffre simple, d’autres une comparaison par produit ou une recherche documentaire. Nous incluons aussi une question ambiguë et une question dont la réponse exige une information absente.

Chaque modèle reçoit le même schéma, les mêmes définitions et les mêmes outils. Nous vérifions les résultats avec des requêtes de référence et les documents sources. Nous observons également les reprises après erreur et les échecs.

Pour la performance, nous mesurons la mémoire GPU et le temps total nécessaire pour obtenir la réponse. Nous distinguons le chargement initial des essais avec un modèle déjà chargé. Nous conservons également la quantification, la taille du contexte et les paramètres utilisés.

Le tableau que vous voyez résume les résultats de cette configuration et de cet ensemble de questions. Il ne permet pas de conclure sur tous les usages possibles du modèle.

Le choix final dépendra du niveau de réussite attendu et des ressources disponibles. Si un modèle échoue régulièrement sur les jointures ou les appels d’outils, sa rapidité seule ne suffira pas pour cet usage. »

### Préparation des résultats

- Compléter le tableau après les essais, avec les noms et configurations exacts.
- Définir `N` et les critères de correction avant de comparer.
- Donner la latence médiane sur plusieurs essais, en incluant les appels d’outils.
- Indiquer les conditions de mesure et les éventuels échecs.
- Montrer un exemple d’erreur observée, seulement si un essai l’a effectivement produite.
- Si les mesures ne sont pas disponibles, titrer la slide « Comment évaluer un petit modèle ? » et présenter le protocole sans conclusion expérimentale.

### Suggestion visuelle

Le tableau complété et un exemple court de résultat vérifié. Éviter une comparaison simultanée de modèles pendant la démo.

### Transition

« Quelle que soit sa taille, le modèle doit fonctionner dans un cadre qui permet de vérifier ses résultats et de limiter ses actions. »

---

## Slide 8 — La fiabilité et les limites

**Durée : 2 minutes, de 16:00 à 18:00**

### À afficher

| Risque | Mesure dans l’application |
| --- | --- |
| Accès excessif aux données | Compte SQL en lecture seule et vues autorisées |
| Calcul ou requête incorrects | Références de contrôle et vérification du périmètre |
| Exécution incontrôlée | Python isolé, ressources et durée limitées |
| Affirmation sans preuve | Sources visibles et incertitude explicite |
| Boucle d’appels | Nombre maximal d’étapes et arrêt contrôlé |

**Une consigne dans le prompt complète les contrôles techniques.**

### Notes orales

« Une première couche concerne les permissions. Le compte de base de données dispose des accès nécessaires à l’analyse. L’application limite les objets accessibles et la quantité de résultats. La lecture seule protège les écritures, mais ne suffit pas à limiter toutes les lectures ni le coût des requêtes.

Pour Python, nous utilisons un environnement isolé, avec un accès limité aux fichiers et au réseau, ainsi qu’une durée d’exécution maximale. Ces restrictions doivent exister dans le système qui exécute le code.

Une autre couche concerne la justesse de l’analyse. Nous vérifions les calculs sur des cas de référence et nous affichons les éléments qui permettent de contrôler la réponse. Un résultat vide ou une erreur d’outil doit apparaître comme tel.

Les documents peuvent aussi contenir du texte qui ressemble à une instruction. L’application doit les traiter comme des sources à consulter, tout en conservant ses propres règles d’accès et d’exécution.

Enfin, l’assistant doit savoir exprimer ce qui manque. Nous pouvons constater une baisse et retrouver une mention de rupture de stock sans avoir établi que cette rupture explique toute la baisse.

Dans la démonstration, nous allons vérifier une conclusion précisément sur cette distinction. »

### Suggestion visuelle

Un tableau court reprenant les contrôles. Montrer les contrôles réellement présents dans la démo et identifier oralement ceux qui restent à implémenter, le cas échéant.

### Transition

« Nous avons le fonctionnement du système et ses critères de vérification. Passons au cas concret. »

---

## Slide 9 — Le scénario de démonstration

**Durée : 2 minutes, de 18:00 à 20:00**

### À afficher

**Un e-commerce fictif**

- PostgreSQL : clients, produits, commandes et lignes de commande.
- Une vue de ventes conforme aux règles métier.
- Documents : rapports commerciaux et retours clients.

**Notre enquête**

1. Quelle est l’évolution du chiffre d’affaires ?
2. Quels produits contribuent le plus à la baisse ?
3. Quels éléments d’explication trouve-t-on dans les documents ?

**À observer : requêtes, résultats, graphique et sources.**

### Notes orales

« Le jeu de données représente un e-commerce fictif. Nous disposons de tables de clients, de produits, de commandes et de lignes de commande, ainsi que d’une vue de ventes destinée à l’analyse. Les documents ajoutent des rapports commerciaux et des retours clients.

Le scénario doit contenir une variation que nous pouvons retrouver dans les données et des documents pertinents pour la période. Les résultats attendus ont été vérifiés avant la séance avec des calculs indépendants de l’assistant.

Nous allons d’abord demander le chiffre d’affaires sur des mois complets. Nous poursuivrons avec les produits qui contribuent à la baisse, puis avec les éléments de contexte dans les documents.

Je conserverai un seul modèle chargé pour cette démonstration. Les comparaisons entre modèles restent dans les mesures présentées précédemment.

Pendant les réponses, nous regarderons l’action choisie par l’assistant et la sortie de l’outil. À la fin, nous vérifierons un chiffre et une affirmation documentaire.

Le point à retenir est le lien entre la question, la méthode et les preuves disponibles. C’est ce lien qui permet d’utiliser l’assistant dans un travail d’analyse. »

### Suggestion visuelle

Les trois questions numérotées, avec une petite liste des sources disponibles. Ouvrir ensuite directement l’application.

### Transition vers la démo

« Commençons par mesurer ce qui se passe dans les ventes. »

---

## Démonstration — 10 minutes

### Étape 1 — Présenter l’environnement

**Durée : 1 minute, de 20:00 à 21:00**

**À montrer :** l’interface, le modèle actif, les outils et les sources disponibles.

**À dire :**

« Le modèle tourne sur notre machine d’inférence. Voici les données et les documents auxquels l’application lui donne accès. Nous allons suivre une seule enquête et regarder les étapes nécessaires pour vérifier ses réponses. »

### Étape 2 — Mesurer l’évolution du chiffre d’affaires

**Durée : 2 minutes, de 21:00 à 23:00**

**Prompt à saisir :**

> Quel est le chiffre d’affaires net pour chacun des six derniers mois complets présents dans la base ? Utilise la définition métier de la vue de ventes. Indique la période couverte et calcule la variation entre les deux derniers mois complets. Montre la requête et les résultats.

**À montrer :**

- L’appel à l’outil SQL et la requête.
- Les montants mensuels et la variation.
- La période et les règles métier retenues.

**À commenter :**

« PostgreSQL calcule les montants. L’assistant les utilise pour restituer l’évolution. Nous vérifions que les mois sont complets et que le périmètre correspond à notre demande. »

**Point de contrôle :** comparer le dernier montant à la valeur de référence préparée avant la séance.

### Étape 3 — Identifier les contributions des produits

**Durée : 3 minutes, de 23:00 à 26:00**

**Prompt à saisir :**

> Sur les deux derniers mois complets, quels produits contribuent le plus à la baisse du chiffre d’affaires ? Calcule pour chaque produit la différence en euros entre ces deux mois. Produis un graphique des principales contributions négatives avec Python. Vérifie que la somme des variations de tous les produits, y compris ceux en croissance, correspond à la variation totale.

**À montrer :**

- Les données agrégées par produit.
- Le graphique et ses unités.
- La vérification de la somme des contributions.

**À commenter :**

« Nous regardons les différences en euros, car elles permettent de retrouver la variation globale. Les produits en croissance compensent une partie des baisses. Le graphique présente les principales contributions négatives, mais la vérification porte sur tous les produits. »

**Point de contrôle :** vérifier le rapprochement avec la variation totale et le traitement des produits absents d’une période.

### Étape 4 — Rechercher le contexte documentaire

**Durée : 2 minutes, de 26:00 à 28:00**

**Prompt à saisir :**

> Recherche dans les rapports commerciaux et les retours clients des passages concernant les produits identifiés et la période étudiée. Cite les documents et les passages utiles. Distingue les faits rapportés, les hypothèses d’explication et les informations manquantes.

**À montrer :** les passages retrouvés, leurs références et la synthèse du modèle.

**À commenter :**

« La recherche documentaire apporte des pistes. Nous vérifions que les passages concernent les bons produits et la bonne période. Une mention dans un rapport ne suffit pas à quantifier son effet sur les ventes. »

**Point de contrôle :** ouvrir une source et vérifier qu’elle soutient l’affirmation associée.

### Étape 5 — Vérifier une conclusion

**Durée : 1 minute, de 28:00 à 29:00**

**Prompt à saisir :**

> Résume ce que nous pouvons affirmer à partir des calculs, ce que les documents suggèrent et les données supplémentaires nécessaires pour confirmer les causes de la baisse.

**À commenter :**

« Nous séparons le constat chiffré des hypothèses. Cette distinction permet à l’analyste de savoir quelles vérifications poursuivre. »

### Étape 6 — Conclusion

**Durée : 1 minute, de 29:00 à 30:00**

**À dire :**

« L’assistant a interrogé les ventes, produit une analyse par produit et retrouvé du contexte documentaire. Nous avons pu examiner la méthode et vérifier une partie des conclusions.

Le choix du modèle repose sur sa réussite dans cet environnement et sur nos contraintes de ressources. La qualité du schéma, les définitions métier et les contrôles de l’application comptent aussi dans le résultat.

La valeur de cet assistant tient à sa capacité à transformer une question métier en une analyse traçable, calculée et vérifiable. »

---

## Préparation avant la séance

### Données et références de contrôle

- Choisir deux mois complets présentant une baisse dans le dataset fictif.
- Fixer la définition du chiffre d’affaires net, le traitement des annulations et des remboursements, ainsi que les limites temporelles.
- Vérifier indépendamment le chiffre d’affaires mensuel, les contributions par produit et leur somme.
- Préparer des documents datés, avec des références stables et des passages pertinents pour les produits étudiés.
- Identifier clairement les données et documents fictifs dans l’application.

### Application

- Tester les prompts exacts et le maintien du contexte entre les questions.
- Charger le modèle avant la séance et vérifier les connexions entre les machines.
- Vérifier les outils SQL, Python et la recherche documentaire.
- Préparer un affichage lisible à la projection, avec les traces utiles faciles à ouvrir.
- Contrôler les permissions et limites annoncées à la slide 8.

### Temps et solution de secours

- Répéter le parcours complet et vérifier qu’il tient dans dix minutes.
- Préparer une capture des résultats et une courte vidéo du parcours.
- Si une étape dépasse son budget, montrer sa capture puis poursuivre l’enquête.
- En cas d’échec, annoncer le problème observé et utiliser les résultats préparés pour expliquer l’étape.
- Garder les essais entre modèles et les détails d’installation pour les échanges après la séance.

## Glossaire pour les notes

| Terme | Signification |
| --- | --- |
| LLM | Large Language Model, modèle de langage de grande taille |
| SQL | Structured Query Language, langage d’interrogation des bases relationnelles |
| RAG | Retrieval-Augmented Generation, génération augmentée par la recherche |
| Orchestrateur | Composant applicatif qui gère les appels aux outils et leur exécution |
| Quantification | Représentation des paramètres avec une précision numérique réduite |
| Latence de bout en bout | Temps entre la demande et la réponse finale, outils compris |

