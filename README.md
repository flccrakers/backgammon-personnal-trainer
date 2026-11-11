# Documentation — Entraîneur de backgammon pour Claude

## Vue d’ensemble

Ce dossier spécifie une application locale qui transforme les parties enregistrées en fichiers `.mat` en exercices ciblés de backgammon. L’application détecte les erreurs de déplacement et les erreurs de décision de cube, conserve le contexte de chaque erreur et propose au joueur de rejouer la décision, avec validation et indication visuelle de la correction.

Le produit comporte trois zones distinctes :

1. **Import et analyse** : surveillance ou balayage d’un répertoire configurable, lecture incrémentale des fichiers et analyse des décisions.
2. **Moteur métier et persistance** : modèle de partie, évaluation des décisions, règles d’unicité et stockage des exercices.
3. **Interface PyQt** : consultation et résolution interactive des exercices, sans logique d’analyse embarquée.

> **Moteur d’analyse.** GnuPG (`gpg`) est un outil cryptographique, pas un moteur de backgammon. Le moteur visé est **GNU Backgammon** (`gnubg`); ne jamais lancer `gpg` comme moteur d’analyse. La compatibilité CLI et la version doivent être testées. Le `.mat` observé de BackgammonGalaxy est un export texte ASCII décrit dans `01-specifications-fonctionnelles.md` et `04-moteur-analyse.md`.

## Principes de conception

- Le moteur et l’accès à la base sont utilisables sans interface graphique.
- PyQt consomme une API publique du moteur; il ne parse pas les `.mat` et n’appelle pas directement le moteur externe.
- Les fichiers sources sont traités de façon incrémentale, traçable et idempotente.
- Les parties et positions sont normalisées dans une représentation canonique, indépendante des conventions d’affichage.
- Une erreur n’est proposée comme exercice qu’avec une position de départ, les dés ou l’état de cube pertinents, la décision réellement prise et une correction de référence.
- Seuls les coups de mouvement et décisions de cube classés « Très mauvais » (`very bad`) par `gnubg` deviennent des exercices; aucun seuil numérique de perte ne décide de l’inclusion.
- Les détails du format observé et les limites d’intégration moteur sont documentés; les variations non couvertes sont validées par tests, jamais devinées.

## Architecture cible

```text
Fichiers .mat
    │
    ▼
Importeur / inventaire ──► Adaptateur de format .mat
                                  │ événements normalisés
                                  ▼
                         Service d’analyse Python
                                  │ appels contrôlés
                                  ▼
                       Adaptateur CLI GNU Backgammon
                                  │ analyses normalisées
                                  ▼
                       Détecteur d’erreurs métier
                                  │
                                  ▼
                        Dépôt / base SQLite
                                  ▲
                                  │ API de service publique
                                  ▼
                            Interface PyQt
```

La communication avec le processus externe se fait via un adaptateur dédié (arguments de processus, flux standard et temporisation). La GUI communique avec le moteur au travers de services Python réutilisables. Elle peut s’exécuter dans un fil de travail pour les opérations longues, mais ne porte aucune logique de persistance SQL directe.

## Lancement rapide

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/bgtrainer          # interface graphique
.venv/bin/bgtrainer-cli scan # scan + analyse sans GUI
```

Détails, décisions, fonctionnalités réellement implémentées (sessions, verrouillage, statistiques gnubg, flèches, fichier unique) et écarts avec la spécification : `docs/07-etat-implementation.md`. En cas de divergence avec `01`–`06`, le doc `07` fait foi.

## Arborescence documentaire

```text
backgammon-trainer-docs/
├── README.md
├── agent.md
├── 01-specifications-fonctionnelles.md
├── 02-architecture.md
├── 03-base-de-donnees.md
├── 04-moteur-analyse.md
├── 05-interface-pyqt.md
├── 06-configuration.md
└── 07-etat-implementation.md
```

## Ordre de lecture et mise en œuvre

1. `agent.md` — mandat, garde-fous et workflow de l’agent développeur.
2. `01-specifications-fonctionnelles.md` — comportement attendu et critères d’acceptation.
3. `02-architecture.md` — frontières de modules et contrat d’API réutilisable.
4. `03-base-de-donnees.md` — entités, relations, unicité et intégrité.
5. `04-moteur-analyse.md` — pipeline d’import/analyse et reprise incrémentale.
6. `05-interface-pyqt.md` — parcours de résolution graphique.
7. `06-configuration.md` — paramètres et valeurs par défaut proposées.

## Prérequis à lever avant le code

- Tester les variantes du format ASCII BackgammonGalaxy observé (métadonnées, parties/tours, coups, cube, résultats) et identifier les variations producteur/version prises en charge.
- Vérifier la CLI non interactive, le format d’entrée/sortie, la version et la licence applicable de `gnubg`; tester le traitement des décisions d’offre, de prise/refus, de passe et de réponse au cube.
- Fixer la profondeur et les options d’analyse; le critère d’exercice est `very bad` pour mouvement et cube, sans seuil numérique de perte.
- Décider si les exercices du mode fichier unique sont filtrés à l’affichage dans la base commune ou isolés dans une session temporaire. Recommandation : filtre sur le match importé, sans créer une base parallèle.

## Hors périmètre documentaire

Ces fichiers spécifient le produit; ils ne contiennent ni code applicatif, ni parseur réel de `.mat`, ni exécutable, ni migration effectivement appliquée. Les exemples de schéma SQL décrivent le contrat de données et devront être adaptés après validation des variantes du format et de la sortie moteur.
