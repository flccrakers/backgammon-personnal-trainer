# 06 — Configuration

> **État réel** : la configuration implémentée est un fichier JSON (`~/.config/backgammon-trainer/config.json`). Voir `07-etat-implementation.md`. L'exemple TOML ci-dessous reste conceptuel.

## 1. Objectifs

La configuration rassemble les répertoires source, le chemin de la base, les options d’analyse du moteur, le critère de sélection des exercices et le comportement de scan. Elle est lue et validée par un module sans dépendance à PyQt. Une valeur invalide produit un message indiquant le paramètre et la correction attendue.

Format proposé : TOML ou JSON versionné. Choisir un seul format pour la première version; TOML est lisible pour édition manuelle si une bibliothèque compatible est disponible, sinon JSON standard évite une dépendance additionnelle. Le modèle de paramètres ci-dessous est conceptuel, pas un fichier applicatif prêt à exécuter.

## 2. Exemple de paramètres

```toml
config_version = 1

[paths]
mat_directory = "~/Backgammon/matches"
include_subdirectories = false
database_path = "~/.local/share/backgammon-trainer/trainer.sqlite3"

[scan]
automatic_on_start = false
interval_minutes = 0           # 0 = pas de surveillance périodique
stable_file_seconds = 3
retry_failed = true

[engine]
# GNU Backgammon (`gnubg`), pas GnuPG (`gpg`); vérifier version et compatibilité CLI.
executable = "gnubg"
timeout_seconds = 120
analysis_profile = "default"
options = []

[analysis]
exercise_classification = "very bad" # classe gnubg requise pour mouvement et cube
metric = "equity_loss" # donnée diagnostique, pas un seuil d’inclusion
near_equal_tolerance = 0.001

[ui]
locale = "fr"
reveal_correction_after_incorrect = true
```

Les valeurs et options exactes du moteur sont à confirmer après sélection de version. L’exemple n’implique pas que toutes les versions GNU Backgammon acceptent `options` sous cette forme.

## 3. Paramètres et validation

| Paramètre | Obligatoire | Règle de validation | Effet |
|---|---:|---|---|
| `config_version` | oui | version supportée | migrations de configuration |
| `paths.mat_directory` | oui pour scan | chemin développé/normalisé; existe et est lisible pour scanner | racine d’import |
| `paths.database_path` | oui | parent créable selon autorisation; répertoire non substitué à un fichier | stockage SQLite |
| `include_subdirectories` | non | booléen | profondeur de découverte |
| `automatic_on_start` | non | booléen | déclenche un scan au démarrage |
| `interval_minutes` | non | entier ≥ 0; zéro désactive la périodicité | scan périodique |
| `stable_file_seconds` | non | durée ≥ 0 | protection fichier en cours d’écriture |
| `retry_failed` | non | booléen | politique de nouvelle tentative |
| `engine.executable` | oui pour analyse | binaire local résolvable; version obtenue et compatible | moteur externe |
| `timeout_seconds` | non | positif et borné raisonnablement | délai d’exécution par requête |
| `analysis_profile` | oui pour reproductibilité | identifiant/version défini | options d’analyse enregistrées |
| `exercise_classification` | non | classe gnubg reconnue; valeur requise dans cette version : `very bad` | sélection commune aux erreurs de mouvement et de cube |
| `metric` | oui | valeur reconnue par la version applicative | interprétation/diagnostic des évaluations, pas sélection par seuil |
| `near_equal_tolerance` | non | nombre fini ≥ 0 | réponses acceptées équivalentes |

La validation ne doit pas créer de répertoire source par erreur. La création du répertoire de données de l’application/parent BDD est explicite et rapportée. Développer `~` et variables d’environnement selon une politique uniforme, puis conserver le chemin effectif normalisé.

## 4. Configuration du binaire GNU Backgammon

- Le nom `gnubg` est la valeur par défaut; l’utilisateur peut fournir un chemin absolu.
- Ne jamais retomber automatiquement sur `gpg` si `gnubg` est absent.
- Au premier démarrage et après modification du chemin, tester présence, lancement/version et compatibilité minimale connue; distinguer « introuvable » de « version non supportée ».
- Enregistrer dans chaque analyse le chemin logique, nom et version effectivement utilisés ainsi que les options qui influent sur le résultat. Ne pas inclure inutilement de paramètres sensibles.
- Les arguments transmis à la CLI doivent être validés et utilisés sans shell. Les options arbitraires ne sont activées que si leur usage est documenté.

## 5. Emplacements et priorité

Ordre recommandé : valeurs par défaut → fichier utilisateur → variables d’environnement explicitement documentées → arguments CLI ponctuels. L’interface peut modifier le fichier utilisateur de manière atomique (écrire fichier temporaire, valider, remplacer) et doit avertir lorsque le changement nécessite redémarrage ou migration. La configuration effective et sa provenance sont consultables dans l’écran « À propos / diagnostic ».

Ne pas persister des chemins propres à un exercice dans le profil partagé. Le mode fichier unique sélectionne un `.mat` pour la session; il ne remplace pas le répertoire source configuré.

## 6. Confidentialité et sauvegardes

La configuration ne contient pas de secrets pour ce cas d’usage. Ne jamais enregistrer de clé GPG ni proposer GnuPG comme moteur de calcul. Limiter les permissions du fichier de configuration et de la BDD aux besoins de l’utilisateur local. Sauvegarder la base avant migration; les fichiers source restent à leur emplacement et ne sont pas modifiés par l’import.

## 7. Cas d’erreur à présenter

- fichier de configuration absent : créer des valeurs par défaut documentées ou guider l’utilisateur;
- version de config inconnue : refuser avec instruction de migration;
- dossier `.mat` manquant/inaccessible : fournir chemin effectif et action possible;
- parent BDD non inscriptible ou BDD verrouillée : ne pas basculer silencieusement vers une autre base;
- binaire manquant ou mauvais moteur (`gpg`) : expliquer que GnuPG n’analyse pas le backgammon et demander installation/configuration de GNU Backgammon;
- classe de sélection ou option incohérente : identifier le champ; dans le périmètre actuel, seuls les cas classés `very bad` sont retenus, sans seuil numérique d’équité.
