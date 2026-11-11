# Journal des versions

Numérotation `MAJEUR.MINEUR.CORRECTIF` : nouvelle fonctionnalité = mineur, correction = correctif.
La version est dans `pyproject.toml` et `src/bgtrainer/__init__.py` (un test vérifie qu'elles concordent).

## [0.2.0] - 2026-11-12
- Icône de l'application (fenêtre, barre des tâches), tirée de `docs/image-trainer.jpeg`.

## [0.1.0] - 2026-11-11
Première version suivie : import et analyse gnubg de fichiers `.mat`, exercices (coups et cube), sessions
d'entraînement avec résumé, relance du scan, filtres « jamais faits » / « échecs > 50 % », comparaison avec le match.
