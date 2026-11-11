# 01 — Spécifications fonctionnelles

> **État réel** : voir `07-etat-implementation.md` pour les écarts (sessions d'entraînement, verrouillage des réponses, statistiques gnubg stockées, remise à zéro de la base).

## 1. Périmètre

L’application importe des matchs depuis un répertoire configurable, calcule ou récupère l’analyse des décisions, enregistre les erreurs retenues et permet de les travailler sous forme d’exercices. Elle prend en charge deux familles d’erreurs :

- **Erreur de mouvement** : coup classé **« Très mauvais » (very bad)** par GNU Backgammon (`gnubg`) après analyse du coup joué.
- **Erreur de cube** : décision (offrir, prendre, passer ou action correspondante) classée **« Très mauvais » (very bad)** par GNU Backgammon (`gnubg`).

Seuls ces deux cas produisent des exercices; les autres classes, même défavorables, sont exclues. Le fichier `.mat` observé est un export texte ASCII de BackgammonGalaxy; la section 2.3 précise sa structure. Les qualités de coup ne sont pas lues dans la source : elles sont calculées par `gnubg`.

## 2. Import des parties `.mat`

### 2.1 Sources

- L’utilisateur configure un répertoire racine; les fichiers admissibles y sont recherchés selon une politique documentée (répertoire direct par défaut, sous-répertoires optionnels).
- L’extension est reconnue sans distinction de casse, mais le parseur doit valider le contenu.
- L’utilisateur peut déclencher un scan manuel. Un scan au démarrage ou périodique est une option configurable; l’application ne surveille pas implicitement le système de fichiers sans paramètre.
- Chaque source est identifiée par son chemin normalisé, sa taille, son horodatage et une empreinte cryptographique de contenu (SHA-256 recommandée). L’empreinte décide si les octets ont changé; le chemin seul ne suffit pas.

### 2.2 Résultat d’import

Le bilan d’un scan indique, par fichier : nouveau et importé, déjà à jour, modifié et réanalysé, invalide/non supporté, erreur de lecture, erreur du moteur ou en attente. Chaque état possède un diagnostic exploitable et n’efface pas les exercices antérieurs.

- Une partie complète est validée et enregistrée de façon atomique.
- Un fichier pouvant contenir plusieurs parties est importé comme une source ayant une ou plusieurs entités match, conformément au format constaté.
- Les métadonnées disponibles (joueurs, date, score, match, identifiant source) sont conservées, sans bloquer l’import si elles sont absentes.
- Un import incomplet ne crée pas de position ou exercice partiellement valide.

### 2.3 Structure `.mat` observée (BackgammonGalaxy)

Le format de référence confirmé est un export texte ASCII, et non un fichier binaire opaque. L’adaptateur prend en charge cette structure :

- Les métadonnées sont des lignes commençant par `;` : site, identifiant de match, noms des deux joueurs, Elo, date/heure, variante, règles de match (notamment match en N points et limite du cube; d’autres champs peuvent être présents).
- Un fichier contient des blocs `Game 1` à `Game N`. Chaque bloc indique le score courant, puis les tours numérotés avec les actions des deux côtés de la ligne.
- Un côté de tour peut contenir un jet de dés sur deux chiffres (par exemple `64`) suivi d’un ou plusieurs déplacements en notation départ/arrivée (par exemple `13/7`). Les doubles comportent plusieurs déplacements; `/0` désigne une sortie du plateau. Les champs de coup peuvent être vides.
- Les actions du cube sont exprimées en texte, notamment `Doubles => 2`, `Takes` et `Drops`. La fin d’une partie indique le résultat, par exemple `Wins 1 point` ou plusieurs points.
- Le parseur normalise les métadonnées, parties, scores, tours, dés, déplacements, actions de cube et résultats; il vérifie la cohérence avant persistance. Il ne suppose pas que chaque côté de tour contient un coup.
- Le `.mat` ne contient **aucune évaluation gnubg** : ni classe (« Très mauvais », etc.), ni qualité analytique. L’application reconstruit les décisions puis demande à `gnubg` de les analyser.

Les champs exacts optionnels et les variations de mise en page doivent être traités avec fixtures, sans recopier dans la documentation des données d’une partie réelle.

## 3. Détection et qualification des erreurs

### 3.1 Erreurs de mouvement

Pour chaque tour avec un jet de dés valide :

1. capturer la position juste avant la décision;
2. enregistrer le joueur au trait et le jet ordonné/non ordonné suivant la convention du format;
3. reconstruire le mouvement réellement joué;
4. obtenir l’évaluation du mouvement joué et les meilleurs candidats de référence;
5. obtenir de `gnubg` la classification de qualité du coup joué;
6. créer un cas d’erreur révisable uniquement si la classification est **« Très mauvais » (very bad)**, avec la décision jouée et la correction de référence.

La génération de correction doit respecter les règles de mouvement, les dés, les coups forcés, les doubles, les ambiguïtés d’ordre de déplacement et les sorties de pions. Les séquences équivalentes menant à la même position finale ne doivent pas être présentées comme distinctes, sauf si l’analyse métier distingue effectivement leur valeur.

### 3.2 Erreurs de cube

À chaque décision pertinente, conserver position, joueur, valeur du cube, propriété/orientation du cube si applicable, score/longueur de match et état de match disponibles. Comparer l’action choisie à l’action optimale évaluée par le moteur (et à la suite correcte, prise/refus, si l’analyse la fournit). Ne créer un exercice que si `gnubg` classe la décision de cube **« Très mauvais » (very bad)**. La règle d’inclusion doit tenir compte de l’état des règles et du contexte de match; si les données requises manquent, marquer la décision non analysable plutôt que d’inventer un contexte.

### 3.3 Critère d’inclusion et égalités

- Le seul critère qui crée un exercice, pour les mouvements comme pour les décisions de cube, est la classe **« Très mauvais » (very bad)** attribuée par `gnubg`. Aucun seuil numérique de perte d’équité ne détermine l’inclusion.
- Le critère peut être exposé comme paramètre configurable pour compatibilité/évolution, mais sa valeur de production est `very bad`; aucune autre classe n’est retenue dans le périmètre actuel.
- Plusieurs meilleures actions dans une tolérance de quasi-égalité peuvent être acceptées comme réponses justes; cette tolérance ne change pas le filtre de classe.
- Une erreur ne peut être créée que si la sortie moteur complète et exploitable fournit la classification requise.
- Version du moteur, niveau/profondeur, options d’analyse et classe de sélection sont attachés à l’analyse. La perte d’équité peut rester une donnée diagnostique, sans servir de seuil d’inclusion.

## 4. Données persistées

Pour un exercice de mouvement : position de départ, joueur actif, dés, coup joué, coup(s) de référence, différence/perte, partie/tour/source, version et paramètres d’analyse.

Pour un exercice de cube : position, joueur, état du cube et contexte de score connus, décision jouée, décision/action optimale, perte et paramètres d’analyse.

Une même erreur logique issue d’une réimportation ne doit pas être dupliquée. Une nouvelle analyse avec des paramètres différents peut être conservée comme une autre révision d’analyse, sans écraser l’historique précédent ni dupliquer silencieusement les exercices.

## 5. Exercice interactif

- L’exercice affiche une position de départ canonique, le joueur au trait, les dés ou l’état du cube, et les informations de contexte pertinentes.
- Pour les mouvements, l’utilisateur saisit/rejoue le coup sur un plateau interactif. L’interface doit représenter les coups composés (plusieurs déplacements), les deux façons d’ordonner le jet lorsque pertinent, les doubles et les coups forcés.
- Pour le cube, l’utilisateur choisit parmi les actions disponibles (par exemple doubler/ne pas doubler, prendre/passer; exactement selon l’état de décision).
- La validation compare l’action normalisée de l’utilisateur avec l’ensemble des réponses acceptées, pas avec une chaîne de texte.
- En cas de réponse correcte : retour positif et action pour continuer. En cas de réponse incorrecte : retour clair; le joueur peut réessayer ou révéler la correction selon le mode choisi.
- La correction affiche le ou les déplacements avec des flèches lisibles (origine → destination) ou une flèche d’action de cube. Elle ne doit pas déplacer silencieusement les pions avant que l’utilisateur ait compris la réponse.
- L’utilisateur peut passer un exercice et revenir à la liste, sans perdre sa progression.
- Enchaînement suivant/précédent et fin de série sont explicites. État d’entraînement (nouveau, en cours, réussi, passé) est conservé de façon indépendante de l’analyse source.

## 6. Mode « un seul fichier `.mat` »

- Un sélecteur permet de choisir un fichier `.mat` directement.
- Si nécessaire, il est importé/analysé avant d’afficher les exercices.
- La liste d’exercices est filtrée strictement par l’identifiant de source et par les parties de ce fichier. Aucun exercice venant d’un autre fichier ne peut apparaître dans la session.
- Les erreurs et parties déjà en base peuvent être réutilisées si l’empreinte du fichier et la révision d’analyse correspondent.
- Si la source a changé, l’application signale la différence et relance l’import/analyse; les résultats obsolètes ne sont pas présentés comme actuels.
- Si aucun exercice n’est trouvé, l’interface distingue « aucun coup classé Très mauvais » de « non analysé/échec d’analyse ».
- Quitter le mode unique ramène au filtre d’entraînement général; cela ne supprime rien de la base.

## 7. Configuration du répertoire

L’utilisateur peut définir le répertoire `.mat`, l’inclusion des sous-répertoires, la fréquence du scan automatique (désactivé par défaut ou explicitement configuré), et le comportement face aux fichiers modifiés. Un répertoire absent ou illisible produit une erreur de configuration claire, pas un écran vide.

Les chemins sont validés à l’activation. Une modification du dossier n’efface ni la BDD ni les imports déjà effectués; elle change le périmètre des futurs scans.

## 8. Critères d’acceptation

1. Deux scans consécutifs d’un même dossier inchangé ne créent aucun doublon et le second est signalé comme à jour.
2. Un fichier modifié est re-détecté par empreinte et réanalysé; l’ancienne version reste traçable.
3. Un fichier invalide est signalé avec motif et n’ajoute pas d’exercice partiel.
4. Une erreur de mouvement stocke et restitue exactement position, dés, mouvement réellement joué et correction(s) acceptée(s).
5. Une erreur de cube stocke et restitue l’état de cube, la décision choisie et la décision de référence.
6. Les réponses équivalentes selon la règle moteur sont acceptées; les mouvements illégaux sont refusés avec une aide compréhensible.
7. Les flèches de correction indiquent l’origine et la destination des déplacements attendus.
8. Le mode fichier unique ne montre que les exercices du fichier choisi et indique les cas sans résultat pour la bonne raison.
9. Une opération d’import/analyse longue n’immobilise pas l’interface PyQt.
10. L’API d’exercice et d’import fonctionne dans un processus Python sans lancer l’interface graphique.
