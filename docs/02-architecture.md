# 02 — Architecture logicielle

## 1. Objectifs et frontières

L’architecture isole les formats de fichiers, les analyses de moteur, le modèle métier, le stockage et l’interface. Le domaine backgammon et les contrats du service ne dépendent ni de PyQt ni du mode d’exécution du moteur externe.

```text
┌──────────────────────────┐       ┌─────────────────────────┐
│ Application PyQt         │       │ CLI / tâches planifiées │
│ vues, contrôleurs, worker│       │ API Python réutilisable │
└─────────────┬────────────┘       └────────────┬────────────┘
              └──────────────┬─────────────────┘
                             ▼
                  Services applicatifs
             Import / analyse / exercices / config
                 ┌───────────┴────────────┐
                 ▼                        ▼
         Domaine normalisé         Dépôts / unité de travail
       position, dés, décisions       SQLite + migrations
                 │                        ▲
        ┌────────┴────────┐               │
        ▼                 ▼               │
 Adaptateur .mat   Adaptateur moteur ──────┘
                   GNU Backgammon CLI
```

La mention initiale « gnupg » est ambiguë. GNU Backgammon (souvent `gnubg`) est l’hypothèse; GnuPG (`gpg`) n’est pas un moteur de jeu. L’adaptateur n’est pas construit avant confirmation et test de la CLI réelle.

## 2. Modules logiques recommandés

Les noms sont indicatifs; conserver ces responsabilités même si l’arborescence change.

| Domaine | Responsabilité | Dépendances autorisées |
|---|---|---|
| `domain` | modèles typés de partie, position, dés, mouvement, cube, analyse et exercice; règles de normalisation/validation | bibliothèque standard, aucune GUI/SQL/CLI |
| `formats.mat` | lecture/validation du `.mat` réel, métadonnées, conversion en événements normalisés | domaine, bibliothèques format si nécessaires |
| `engine` | interface de calcul et adaptateur processus GNU Backgammon; interprétation versionnée de ses réponses | domaine, adaptateur externe |
| `analysis` | orchestration d’analyse, comparaison des actions et filtre `very bad`; production des cas d’erreur | domaine, port moteur |
| `repositories` | accès aux entités, transactions, migrations, requêtes exercice et dédoublonnage | domaine, SQLite |
| `services` | cas d’utilisation publics : scanner/importer, analyser, lister/valider exercice | domaine, formats, moteur, dépôts |
| `config` | lecture, validation, chemins effectifs et options | standard library |
| `ui` | vues PyQt, modèle de présentation, worker/signaux, rendu plateau | services publics seulement |

## 3. API Python réutilisable

Exposer une façade stable de service. Les signatures concrètes peuvent être typées selon le domaine, mais le contrat doit inclure :

- `scan_sources(config, target=None)`: découvre les `.mat`, compare inventaire/empreintes et retourne un rapport par fichier.
- `import_source(path, force=False)`: valide source, parse, enregistre des parties et retourne leur identité ainsi que les diagnostics.
- `analyze_match(match_id, analysis_profile=None)`: exécute ou réutilise une analyse et retourne résumé, erreurs créées et état.
- `list_exercises(filters)`: filtre par type, état, source/match et ordre de sélection; le mode unique exige un identifiant de source.
- `get_exercise(exercise_id)`: retourne toutes les données canoniques pour rendre et tenter l’exercice.
- `submit_attempt(exercise_id, normalized_answer)`: valide la réponse côté service et retourne statut, explication, flèches/référence selon la politique de révélation.
- `set_exercise_status(...)`: met à jour la progression sans modifier l’analyse.

Les retours sont des objets de domaine/DTO sérialisables et ne révèlent pas d’objet SQLite ou widget. Les erreurs sont typées : configuration, source illisible, format non supporté, moteur indisponible, timeout, résultat mal formé, BDD/migration et conflit de données. La façade ne requiert pas la création d’une application PyQt.

## 4. Exécution du moteur externe

L’analyse dépend d’un port, par exemple conceptuel `evaluate(position, dice, context)`. Son adaptateur CLI :

- identifie le chemin/version du binaire;
- passe les arguments en liste sans interpolation shell;
- fixe un répertoire de travail contrôlé, un timeout et des plafonds de sortie;
- collecte code de retour, stdout et stderr;
- normalise les résultats et rejette une sortie incomplète/non reconnue;
- ne laisse pas les détails propres à GNU Backgammon franchir la frontière moteur.

La syntaxe CLI ne doit pas être présumée : la figer à partir de la documentation/version installée et de tests d’intégration.

## 5. Interface et concurrence

PyQt appelle les services au travers d’un worker ou mécanisme asynchrone compatible avec sa boucle d’événements. Le worker renvoie progression, rapport et erreur via signaux/retours sûrs. Les widgets n’effectuent ni analyse moteur, ni scan de dossier, ni requête SQL directe.

Toute session SQLite respecte une unité de travail courte. Ne pas partager une connexion non sûre entre threads; un worker crée/obtient sa propre session conformément à la bibliothèque choisie. Les opérations qui modifient les données sont transactionnelles et leur résultat est transmis à la GUI.

## 6. Données et migrations

SQLite est la valeur par défaut recommandée pour une application locale mono-utilisateur; le chemin est configurable. La couche dépôts est la seule qui connaît le SQL. Les migrations sont numérotées, vérifiées au démarrage et sauvegardables avant migration. Les opérations d’import par partie et l’enregistrement du résultat d’analyse utilisent des transactions explicites.

## 7. Flux d’import/analyse

1. Le service de scan découvre la source et calcule l’empreinte.
2. L’inventaire détermine nouveau, inchangé, modifié ou précédemment échoué à reprendre.
3. Le parseur `.mat` produit des événements/domaines normalisés.
4. Le validateur de domaine vérifie cohérence et convention de plateau.
5. Le moteur externe évalue les décisions admissibles.
6. Le détecteur ne crée des erreurs que pour les classifications `very bad` renvoyées par `gnubg`, pour les deux types d’erreur.
7. Le dépôt enregistre révision d’analyse, décisions et erreurs dans une transaction.
8. Le rapport de scan expose les états, sans confondre « aucun problème » et « pas analysé ».

## 8. Tests et substituabilité

- Tests unitaires domaine: orientation, coups composés, équivalence, cube et filtre strict `very bad`.
- Tests parseur: fixtures exactes des versions `.mat` supportées, corruption, champs optionnels.
- Tests du port moteur avec faux adaptateur déterministe, puis tests d’intégration versionnés avec vrai binaire.
- Tests dépôts: migrations, clés uniques, transactions, concurrence acceptable et recherche par source.
- Tests de service sans GUI; tests UI séparés et limités aux interactions.

Le faux moteur ne remplace pas les tests d’intégration qui confirment une installation compatible.
