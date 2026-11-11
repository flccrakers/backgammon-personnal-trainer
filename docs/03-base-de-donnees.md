# 03 — Base de données

## 1. Choix et invariants

SQLite est le choix initial pour le stockage local; le chemin est défini dans la configuration. Schéma versionné par migrations. Activer les clés étrangères et utiliser des transactions explicites. Le DDL ci-dessous est une proposition contractuelle à adapter après validation des variantes du format ASCII observé et de la sortie moteur réelle.

Invariants :

- toutes les positions suivent une seule convention canonique et sont versionnées;
- un exercice référence une décision et une analyse identifiable; seules les classes `very bad` de gnubg sont persistées comme erreurs/exercices, pour mouvements et cube;
- une source modifiée ne détruit pas silencieusement la révision antérieure;
- les événements de jeu importés et l’état d’entraînement sont séparés;
- une valeur inconnue est `NULL` ou marquée indisponible, jamais remplacée par une valeur devinée.

## 2. Entités et relations

- `source_file`: chemin normalisé, empreinte, taille, dates et état d’import.
- `match`: partie/match importé depuis une révision de source; peut représenter un bloc de partie selon le format.
- `position`: snapshot avant décision, joueur actif, sérialisation canonique et version de convention.
- `dice_roll`: jet associé au tour/à la décision; deux dés structurés et validation 1–6.
- `played_move`: mouvement effectivement choisi, représentation canonique et métadonnées d’évaluation.
- `move_error`: écart d’un mouvement joué à un candidat de référence, perte et identifiant d’analyse.
- `cube_error`: état/décision du cube, choix effectué et choix de référence, perte.
- `analysis_run`: version moteur et profil de calcul, critère de sélection `very bad`, statut et date.
- `exercise_progress`: état du joueur, nombre de tentatives, résultat récent et dates; distinct de la vérité importée.

## 3. Proposition de schéma SQL

DDL indicatif pour la documentation; prévoir migrations réelles et vérifier les fonctions/contraintes disponibles dans la version SQLite ciblée.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE source_file (
    id              INTEGER PRIMARY KEY,
    canonical_path  TEXT NOT NULL,
    content_sha256  TEXT NOT NULL,
    byte_size       INTEGER NOT NULL CHECK (byte_size >= 0),
    mtime_utc       TEXT,
    format_version  TEXT,
    status          TEXT NOT NULL CHECK (status IN
                    ('discovered','imported','unchanged','failed','unsupported')),
    last_error      TEXT,
    imported_at_utc TEXT,
    UNIQUE (canonical_path, content_sha256)
);

CREATE TABLE match_record (
    id              INTEGER PRIMARY KEY,
    source_file_id  INTEGER NOT NULL REFERENCES source_file(id),
    source_match_key TEXT NOT NULL,
    player_0        TEXT,
    player_1        TEXT,
    match_date      TEXT,
    score_0         INTEGER,
    score_1         INTEGER,
    match_length    INTEGER,
    raw_metadata    TEXT,
    UNIQUE (source_file_id, source_match_key)
);

CREATE TABLE analysis_run (
    id                  INTEGER PRIMARY KEY,
    match_id            INTEGER NOT NULL REFERENCES match_record(id),
    engine_name         TEXT NOT NULL,
    engine_version      TEXT NOT NULL,
    profile_fingerprint TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                        ('pending','running','complete','failed','partial')),
    started_at_utc      TEXT,
    completed_at_utc    TEXT,
    error_text          TEXT,
    UNIQUE (match_id, profile_fingerprint)
);

CREATE TABLE position_snapshot (
    id                    INTEGER PRIMARY KEY,
    match_id              INTEGER NOT NULL REFERENCES match_record(id),
    source_decision_key   TEXT NOT NULL,
    turn_number           INTEGER,
    decision_index        INTEGER NOT NULL,
    player_to_move        INTEGER NOT NULL CHECK (player_to_move IN (0,1)),
    board_encoding        TEXT NOT NULL,
    board_schema_version  INTEGER NOT NULL,
    cube_value            INTEGER NOT NULL DEFAULT 1 CHECK (cube_value >= 1),
    cube_owner            INTEGER CHECK (cube_owner IN (0,1) OR cube_owner IS NULL),
    crawford              INTEGER,
    score_0               INTEGER,
    score_1               INTEGER,
    match_length          INTEGER,
    UNIQUE (match_id, source_decision_key)
);

CREATE TABLE dice_roll (
    id          INTEGER PRIMARY KEY,
    position_id INTEGER NOT NULL UNIQUE REFERENCES position_snapshot(id),
    die_1       INTEGER NOT NULL CHECK (die_1 BETWEEN 1 AND 6),
    die_2       INTEGER NOT NULL CHECK (die_2 BETWEEN 1 AND 6),
    is_double   INTEGER NOT NULL CHECK (is_double IN (0,1)),
    CHECK ((die_1 = die_2) = is_double)
);

CREATE TABLE played_move (
    id                INTEGER PRIMARY KEY,
    position_id       INTEGER NOT NULL REFERENCES position_snapshot(id),
    analysis_run_id   INTEGER REFERENCES analysis_run(id),
    move_encoding     TEXT NOT NULL,
    resulting_board   TEXT,
    evaluation_value  REAL,
    evaluation_metric TEXT,
    source_move_key   TEXT,
    UNIQUE (position_id, source_move_key)
);

CREATE TABLE move_error (
    id                    INTEGER PRIMARY KEY,
    position_id           INTEGER NOT NULL REFERENCES position_snapshot(id),
    played_move_id        INTEGER NOT NULL REFERENCES played_move(id),
    analysis_run_id       INTEGER NOT NULL REFERENCES analysis_run(id),
    best_move_encoding   TEXT NOT NULL,
    accepted_answers_json TEXT NOT NULL,
    equity_loss           REAL NOT NULL CHECK (equity_loss >= 0),
    metric                TEXT NOT NULL,
    classification        TEXT NOT NULL CHECK (classification = 'very bad'),
    UNIQUE (position_id, analysis_run_id, played_move_id)
);

CREATE TABLE cube_error (
    id                    INTEGER PRIMARY KEY,
    position_id           INTEGER NOT NULL REFERENCES position_snapshot(id),
    analysis_run_id       INTEGER NOT NULL REFERENCES analysis_run(id),
    action_taken          TEXT NOT NULL,
    best_action           TEXT NOT NULL,
    response_if_double    TEXT,
    equity_loss           REAL NOT NULL CHECK (equity_loss >= 0),
    metric                TEXT NOT NULL,
    classification        TEXT NOT NULL CHECK (classification = 'very bad'),
    UNIQUE (position_id, analysis_run_id)
);

CREATE TABLE exercise_progress (
    id              INTEGER PRIMARY KEY,
    exercise_type   TEXT NOT NULL CHECK (exercise_type IN ('move','cube')),
    exercise_id     INTEGER NOT NULL,
    state           TEXT NOT NULL DEFAULT 'new'
                    CHECK (state IN ('new','in_progress','correct','skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_attempt_at_utc TEXT,
    updated_at_utc  TEXT NOT NULL,
    UNIQUE (exercise_type, exercise_id)
);

CREATE INDEX idx_match_source ON match_record(source_file_id);
CREATE INDEX idx_position_match ON position_snapshot(match_id, decision_index);
CREATE INDEX idx_move_error_run ON move_error(analysis_run_id);
CREATE INDEX idx_cube_error_run ON cube_error(analysis_run_id);
```

### Notes sur le DDL

- `source_match_key` et `source_decision_key` sont des identifiants stables dérivés d’identifiants source si disponibles; sinon calculés depuis l’ordre et les données normalisées, avec stratégie versionnée. Ne pas inclure l’empreinte du fichier dans une clé qui doit conserver l’identité d’un match identique après réimport.
- La contrainte `source_move_key` peut être nullable selon SQLite; les moteurs SQL traitent généralement plusieurs `NULL` comme distincts. Ajouter une clé déterministe si le format offre plusieurs séquences.
- `exercise_progress` utilise une référence polymorphe qui ne peut pas avoir une clé étrangère SQL simple. Alternative recommandée si intégrité stricte : table commune `exercise` avec clés vers l’erreur mouvement ou cube et clé étrangère de progression vers `exercise`. Choisir et documenter avant migration initiale.
- Les positions ou résultats d’analyse JSON doivent être validés par le domaine; SQL seul ne garantit pas leur structure. Les tables d’erreur ne reçoivent que les décisions dont la classe gnubg est `very bad`; les valeurs d’équité/metric peuvent être conservées à titre diagnostique, mais aucun seuil numérique ne gouverne l’inclusion.
- La sérialisation de `accepted_answers_json` est canonique, versionnée et doit pouvoir être reconstruite depuis une analyse.

## 4. Unicité et réimportation

- Identité fichier-version : (`canonical_path`, `content_sha256`). Les copies du même contenu à des chemins différents restent des sources distinctes, sauf décision produit de dédupliquer par contenu.
- Identité match : (`source_file_id`, `source_match_key`). Un fichier modifié crée une nouvelle révision de source ou met à jour l’inventaire de source tout en gardant un historique versionné; arrêter cette décision dans la stratégie de migration avant implémentation.
- Identité décision : (`match_id`, `source_decision_key`). Le type d’événement (mouvement/cube) est lié à la décision.
- Unicité d’erreur : décision + révision/profil d’analyse + coup joué (mouvement), ou décision + profil d’analyse (cube). Nouvelle version moteur/profil produit une nouvelle analyse, pas un écrasement opaque.
- Progression d’exercice est séparée par identifiant logique d’exercice. Si une analyse retire une erreur, garder la progression comme historique ou marquer l’exercice obsolète; ne pas supprimer en cascade sans règle explicite.

## 5. Transactions, rétention et intégrité

- Une unité atomique minimale est l’enregistrement d’une partie et de ses décisions normalisées. Un échec rollbacke l’unité concernée et enregistre l’état d’échec au niveau source hors de la transaction échouée.
- L’analyse est un artefact distinct; échec moteur laisse les données importées consultables, mais sans faux exercice.
- Activer journaling adapté à l’usage, fermer proprement les connexions, gérer les verrous et fournir sauvegarde/restauration de base avant migrations destructives.
- Des suppressions de source doivent être explicites. Le scan ne supprime pas automatiquement les parties parce qu’un fichier a disparu du répertoire.
