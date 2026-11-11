# 07 — État de l'implémentation et lancement

## 1. Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"     # installe PyQt6, pytest et les commandes bgtrainer
```

Prérequis : Python >= 3.10 et GNU Backgammon (`gnubg`, testé en 1.06.002, `/usr/games/gnubg`).

## 2. Lancement

```bash
./lancer.sh                         # interface graphique (crée le venv si besoin)
.venv/bin/bgtrainer                 # équivalent, venv déjà créé
.venv/bin/bgtrainer-cli scan        # import + analyse du répertoire configuré (sans GUI)
.venv/bin/bgtrainer-cli scan --limit 5   # essai sur les 5 premiers fichiers
.venv/bin/bgtrainer-cli stats       # nombre d'erreurs par joueur
.venv/bin/pytest -q tests           # tests
```

Premier usage : GUI > « Paramètres » > choisir le répertoire `.mat` (ex. `~/Documents/bg-mat`) > Enregistrer > « Scanner le répertoire ». L'analyse à 2 plies prend environ 40 à 75 s par match, en parallèle (`engine_workers`). Un second scan ne retraite que les fichiers nouveaux ou modifiés. Le répertoire d'exemple contient 835 fichiers (31 doublons `(1).mat`) : prévoir une à deux heures pour le premier scan complet.

## 3. Emplacements

- Configuration : `~/.config/backgammon-trainer/config.json` (JSON versionné, remplace l'exemple TOML de `06`).
- Base : `~/.local/share/backgammon-trainer/trainer.sqlite3` (migrations par `PRAGMA user_version`, sauvegarde `.bak-vN` avant migration).
- Les `.mat` ne sont jamais modifiés ; gnubg travaille sur une copie temporaire.

Paramètres : `mat_directory`, `include_subdirectories`, `database_path`, `engine_executable`, `engine_plies` (2), `engine_workers`, `engine_timeout_seconds`, `near_equal_tolerance`, `reveal_correction_after_incorrect`, `show_match_move` (flèches grises, défaut `false`), `selected_players`.

## 4. Décisions prises

- Moteur : GNU Backgammon (`gnubg`), confirmé. Profondeur : 2 plies.
- Intégration : gnubg est lancé en sous-processus (`gnubg -t -q -p gnubg_script.py`, sans shell). Le script interne appelle l'API Python embarquée `gnubg.match()` et écrit un JSON ; la classe `skill` (« very bad ») et les candidats viennent directement de gnubg. Aucune lecture de texte libre.
- Chemin de base : global à l'utilisateur.
- Exercices : les erreurs de **tous** les joueurs sont stockées ; l'interface permet de choisir (cases à cocher) les joueurs dont on travaille les erreurs.
- Doublons : identité d'un match = SHA-256 du contenu. Les copies `(1).mat` sont marquées `duplicate`.
- Cube : les décisions couvertes sont doubler, ne pas doubler (double manqué, `cube-skill` de gnubg), prendre, passer.
- Interface : noir et blanc pour le plateau et les widgets ; seules couleurs utilisées : vert/rouge pour les résultats et les flèches de correction (voir 4 quater). Thème complet reporté.

## 4 bis. Sessions d'entraînement

- « Nouvelle session » fige la liste d'exercices courante (filtres, joueurs, ordre) ; les filtres sont verrouillés pendant la session. Démarrer une nouvelle session marque une session encore ouverte comme `abandoned` (résultats conservés).
- Chaque tentative, correction vue ou « Passer » est enregistrée (`session_event`, migration 2) avec l'horodatage ; la session reste dans `training_session`.
- Résultat par exercice : `first_try` (réussi du 1er essai, sans correction vue), `retry` (réussi après une erreur), `failed` (correction vue avant la réussite, ou erreur sans réussite), `skipped`, `unanswered`.
- Score de session = % d'exercices `first_try`. Le résumé final compare avec la session terminée précédente ; « Historique » liste toutes les sessions (date, compteurs, score, barre de progression).
- Feedback : bandeau vert « CORRECT », rouge « INCORRECT » ; un coup illégal s'affiche en rouge sans compter comme tentative.
- La session se termine automatiquement quand tous les exercices sont traités, ou via « Terminer la session ».
- API : `start_session`, `submit_attempt(..., session_id)`, `record_reveal`, `record_skip`, `session_outcomes`, `session_summary`, `finish_session`, `list_sessions`.

## 4 ter. Verrouillage, statistiques gnubg, remise à zéro

- **Verrou en session** : une fois la réponse validée (ou la correction consultée), l'exercice est verrouillé pour la session ; le service refuse toute nouvelle tentative (`AttemptResult.locked`). En revisitant un exercice verrouillé, l'interface réaffiche votre réponse, le résultat et les statistiques en lecture seule. Hors session, on peut toujours réessayer. « Voir la correction » demande confirmation (compté comme échec).
- **Statistiques gnubg** : après validation (succès ou erreur) un panneau affiche, pour les coups : équité, écart au meilleur, probabilités de gain/gammon/backgammon et de perte, profondeur d'évaluation, avec marqueurs `*` (meilleur) et `J` (joué). Pour le cube : équités ND, D/T, D/P, probabilités et meilleure décision. Jusqu'à 12 coups sont conservés (plus le coup joué).
- **Stockage** : ces données sont calculées par gnubg lors du scan et stockées dans `exercise.extra_json` (clé `analysis`). Le profil d'analyse passe à `builder=3, script=2` : une base scannée avec l'ancienne version sera ré-analysée au prochain scan (ou vider la base).
- **Remise à zéro** : Paramètres > « Vider la base et refaire le scan… » (confirmation). Supprime sources, matchs, analyses, exercices et progression, avec sauvegarde `trainer.bak-reset` ; l'historique des sessions est conservé sauf si la case est décochée. Les `.mat` ne sont pas modifiés. API : `TrainerService.reset_database(keep_sessions=True)`.

## 4 quater. Indication de travail et flèches

- Pendant un scan (dossier ou fichier unique) : barre de progression (animée tant que gnubg travaille, car il ne fournit pas d'avancement interne), libellé de l'étape, compteur de fichiers, temps écoulé, curseur « occupé » et bouton « Annuler ».
- Flèches de correction : vert = meilleur coup, rouge pointillé = votre réponse (si fausse), gris = coup joué en match (case à cocher, désactivée par défaut, option `show_match_move`). Elles partent du pion du dessus de la pile de départ vers l'arrivée, sans être horizontales.

## 4 quinquies. Affichage du verrouillage en session

- Dans la liste, un exercice raté est entièrement en rouge (« ERREUR [verrouillé] »), un exercice réussi en vert (« RÉUSSI [verrouillé] »), un exercice passé en gris. La sélection est marquée par un cadre noir, pour ne pas masquer la couleur.
- Un exercice verrouillé est en lecture seule : plateau, boutons Valider/Recommencer/Voir la correction/Passer désactivés, et le service refuse toute nouvelle tentative. En y revenant, on revoit sa réponse, le résultat et les statistiques gnubg.

## 4 sexies. Plateau, dés, fichier unique, résultats hors session

- **Plateau** : dessiné en QPainter, il s'agrandit avec la fenêtre (échelle uniforme, centré) ; les clics sont convertis avec la même échelle. Saisie d'un coup : clic sur le pion puis sur la destination (barre = clic sur la barre, sortie = zone « Sortis »). Les destinations légales sont encadrées. « Annuler un pas » et « Recommencer » sont disponibles avant validation.
- **Dés** : dessinés comme de vrais dés (points) à droite du plateau ; mention « double : x4 » pour un double. Aucun dé pour un exercice de cube.
- **Mode fichier unique** : « Fichier unique… » ouvre un `.mat`, l'importe et l'analyse si nécessaire (barre de progression), puis **démarre automatiquement une session** sur les exercices de ce fichier seul. Si une session est en cours, confirmation puis elle est terminée avant d'ouvrir le fichier. Fichier sans exercice ou analyse en échec : aucune session créée, le message distingue « aucun coup très mauvais », « non analysé », « échec d'analyse », « fichier invalide ». « Quitter fichier unique » termine la session après confirmation et revient au filtre général. Le scan d'un dossier ne crée pas de session (bouton « Nouvelle session »).
- **Hors session** : on peut réessayer un exercice. La liste est colorée (rouge = « raté (à refaire) », vert = « réussi », gris = « passé ») et le bandeau d'erreur rappelle que « Nouvelle session » compte et verrouille les résultats.
- **Filtres** : coups/cube, joueurs (cases à cocher, « Tous »/« Aucun », erreurs de tous les joueurs stockées), état (tous, à faire, réussis), ordre (par partie, plus grosse perte, aléatoire).

## 5. Convention de plateau (version 1)

Position vue du joueur au trait ; `mine`/`opp` = 25 entiers, index 0-23 = points 1-24, index 24 = barre. Le point 24 est le plus éloigné de la sortie. Pas = (origine, destination), barre = 25, sortie = 0. Validée en rejouant 1103 coups réels contre les positions de gnubg (aucun écart).

## 6. Structure du code

```text
src/bgtrainer/
  domain/board.py            plateau, coups légaux
  formats/mat.py             parseur .mat (métadonnées, structure, validation)
  engine/gnubg_adapter.py    sous-processus + sonde de version
  engine/gnubg_script.py     script exécuté dans gnubg
  analysis/builder.py        JSON gnubg -> exercices very bad
  repositories/db.py         schéma et migrations
  services/api.py            façade (scan, exercices, tentatives)
  config/settings.py         configuration
  ui/                        PyQt6 (fenêtre, plateau QPainter)
  cli.py, __main__.py
```

## 7. Écarts avec les documents 01-06

- Schéma SQL réel (`repositories/db.py`) : table unique `exercise` (mouvement et cube) avec `kind`, progression indexée par `logical_key` ; tables `move_error`/`cube_error`/`position_snapshot` non créées. Le mode fichier unique filtre par SHA-256 du match.
- Format du fichier de configuration : JSON au lieu de TOML.
- Pas de surveillance périodique du répertoire ni de scan au démarrage (scan manuel uniquement).
- Seuls les noms `very bad` sont retenus ; la perte d'équité est un diagnostic.

## 8. Limites connues

- Tests présents : règles du plateau, sessions (verrou, résultats, historique) et remise à zéro de la base. À ajouter : parseur, import idempotent, fichier modifié/tronqué, interface (vérifiée jusqu'ici par scripts hors écran et captures).
- Les flèches de correction n'affichent que la première réponse acceptée ; barre et sortie non testées visuellement.
- Un exercice « passé » n'est pas verrouillé en session : on peut y revenir et le jouer.
- Pas d'avancement interne gnubg : la barre de progression d'un fichier unique est animée, pas en pourcentage.
- Scans précédant la migration `builder=3/script=2` : exercices sans statistiques gnubg (message explicite) tant que la base n'est pas ré-analysée.
- Interface non essayée à la main sur tous les cas (barre/sortie, doubles, fenêtre très petite).
- Annulation d'un scan : les analyses gnubg en cours se terminent avant l'arrêt.
- Mouvements « sans coup légal » : pas d'exercice.
