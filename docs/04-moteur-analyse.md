# 04 — Moteur d’analyse et import incrémental

## 1. Précondition bloquante : choix du moteur

Le besoin nomme « gnupg »; `gpg` (GnuPG) chiffre/signe des données et ne calcule pas les coups de backgammon. La présente spécification suppose **GNU Backgammon (`gnubg`)**. Avant développement, confirmer cette interprétation et vérifier la CLI de la version ciblée, son mode non interactif et la forme des évaluations retournées. Le parseur applicatif lit l’export ASCII; GNU Backgammon reçoit les positions/décisions normalisées, pas le `.mat` brut. Aucun nom de commande ni format d’échange CLI ne sont tenus pour acquis ici; le `.mat` brut est traité par l’adaptateur de format dédié.

## 2. Pipeline de traitement

1. **Découverte** : énumérer les fichiers selon configuration; ignorer les fichiers temporaires explicitement définis et les extensions non admissibles.
2. **Stabilisation facultative** : pour un dossier surveillé, éviter de lire un fichier encore en écriture (taille/mtime stables pendant la fenêtre configurée ou traitement uniquement au scan manuel).
3. **Inventaire** : normaliser chemin, vérifier droits, lire taille et dates, calculer SHA-256 en flux.
4. **Décision incrémentale** : même chemin + même empreinte + même profil terminé → à jour; contenu modifié → nouvelle révision; échec antérieur → réessayer selon politique; profil d’analyse différent → réutiliser l’import normalisé et recalculer uniquement l’analyse si possible.
5. **Parsing `.mat`** : reconnaître l’export texte ASCII BackgammonGalaxy décrit à la section 3; décoder parties et événements. Refuser toute structure non prise en charge avec statut `unsupported`; ne pas importer de champs partiels en base.
6. **Normalisation** : vérifier joueurs, ordre des tours, orientation/couleur, états de plateau, dés, mouvements et transitions; convertir vers la représentation canonique.
7. **Persistance de l’import** : enregistrer source, matchs, snapshots, jets et coups joués dans une transaction selon unité choisie.
8. **Évaluation** : constituer une demande d’analyse pour chaque décision pertinente; transmettre au moteur via adaptateur CLI.
9. **Qualification** : normaliser les résultats et retenir exclusivement les coups de mouvement et décisions de cube classés `very bad` par `gnubg`; ne pas appliquer de seuil numérique de perte pour sélectionner les exercices.
10. **Persistance d’analyse** : enregistrer paramètres/version, valeurs, erreurs et réponses acceptables; terminer la révision dans une transaction.
11. **Rapport** : par fichier, exposer statut, nombre de parties/décisions traitées, erreurs trouvées, durée et diagnostics expurgés.

## 3. Adaptateur de format `.mat`

Le format réel observé est un export texte ASCII de BackgammonGalaxy. Le parseur de référence prend en charge cette structure; les variations et cas incomplets/corrompus restent à éprouver par fixtures.

- Les métadonnées sont des lignes commençant par `;` : site, identifiant de match, joueurs, Elo, date/heure, variante, match en N points et limite de cube. Les champs facultatifs supplémentaires sont conservés s’ils sont reconnus.
- Les blocs `Game 1` à `Game N` portent le score courant. Chaque tour est numéroté et présente deux côtés de ligne. Chaque côté peut être vide ou contenir des dés sur deux chiffres (ex. `64`) puis les coups en notation départ/arrivée (ex. `13/7`).
- Un double se traduit par plusieurs déplacements dans le même tour; `/0` indique une sortie. Les champs de coup vides ne sont pas des erreurs de syntaxe par eux-mêmes.
- Les actions de cube sont inscrites en texte, notamment `Doubles => 2`, `Takes` et `Drops`. La partie se termine par un résultat textuel du type `Wins 1 point` (ou un autre nombre de points).
- L’adaptateur produit des événements normalisés indépendants de la mise en page : métadonnées/match, score, tours, côté/joueur, dés, déplacements, actions de cube et résultat. Il garde l’ordre source et valide transitions, nombres et champs disponibles avant persistance.
- Ce `.mat` ASCII ne contient **aucune évaluation gnubg** : les classes de qualité ne sont jamais extraites du fichier. Elles sont obtenues séparément par l’analyse moteur.

Ne pas recopier dans la documentation le contenu du fichier source; les fixtures de test doivent être distinctes et anonymisées. Distinguer structure non prise en charge, corruption, encodage invalide et fichier vide.

## 4. Adaptateur GNU Backgammon CLI

L’adaptateur constitue une frontière d’intégration, responsable de :

- localiser le binaire configuré et obtenir/valider sa version;
- rendre reproductible le profil (niveau, profondeur, prune, options de cube si prises en charge);
- traduire une position/décision canonique vers l’entrée acceptée par la version ciblée;
- exécuter les requêtes sans shell, avec timeout, limites de ressources/sortie et contrôle du code retour;
- analyser la sortie par format/version et interpréter les classifications `very bad` fournies par gnubg; éviter l’extraction fragile par texte libre si un format structuré existe;
- convertir mesures en unité commune et conserver les candidats dans l’ordre renvoyé;
- rejeter sorties tronquées, ambiguës ou incompatibles et attacher diagnostic/version au run.

Tester l’adaptateur avec des positions connues et des décisions de référence. Distinguer le résultat « mouvement légal mais faible » du résultat « entrée moteur invalide ».

## 5. Détection des erreurs

### Mouvement

Pour chaque décision, appeler l’analyse avec la position avant jet et le jet. Identifier le mouvement réel dans la liste analysée (ou l’évaluer spécifiquement si la CLI le permet). Demander au moteur la classification de qualité de la décision jouée et les meilleurs candidats de référence. Créer un exercice de mouvement uniquement si `gnubg` fournit la classe **`very bad` (« Très mauvais »)** et un résultat complet/exploitable. La perte d’équité peut être conservée comme diagnostic, mais aucun seuil numérique ne sélectionne l’exercice. Conserver les meilleures réponses dans une tolérance de quasi-égalité. Si le coup joué est absent ou inexploitable, la décision est non analysable; ne pas lui attribuer arbitrairement une classe.

### Cube

Fournir l’état exact du cube, joueur, score/règles disponibles et action envisagée. Demander à `gnubg` d’évaluer l’action prise et de la classer; créer un exercice uniquement si la classe est **`very bad` (« Très mauvais »)**. Les valeurs d’équité peuvent être conservées à titre diagnostique, sans seuil numérique d’inclusion. Les réponses take/pass après double doivent être interprétées dans le bon état de cube. Si le moteur nécessite des informations de match manquantes, enregistrer `not_analyzable` au niveau de la décision, pas une erreur supposée.

## 6. Nouveaux fichiers, modifications et reprise

- Empreinte du contenu plutôt que mtime seul; conserver `mtime` comme indice, pas preuve d’identité.
- Incrémentalité en deux étages : réutiliser les événements importés quand l’empreinte et le parseur correspondent; réutiliser l’analyse quand l’empreinte du profil et la version moteur correspondent.
- Une analyse nouvelle (classe de sélection/profondeur/version) crée une révision distincte. Le profil stable doit couvrir toutes options influant sur l’évaluation et la normalisation; le filtre d’exercices reste `very bad` pour les deux types d’erreur.
- Utiliser statut persistant (`discovered`, `importing`, `imported`, `analyzing`, `complete`, `failed`, `unsupported`) ou équivalent, horodatage et tentative. À la reprise, traiter les états non terminés sans duplicata.
- Écriture transactionnelle et clés idempotentes; ne marquer `complete` qu’après validation et commit de tous les résultats attendus.
- Un fichier disparu ne supprime pas le contenu historique. Un fichier modifié conserve l’ancienne empreinte/révision ou ses données demeurent clairement historisées.
- Prévoir un verrou contre deux scans concurrents du même fichier; un scan global peut continuer sur les autres fichiers après une erreur locale.

## 7. Observabilité et erreurs

Journaliser identifiants source/match/run, phase, durée, code retour et message technique limité. Éviter de journaliser toutes les données privées des parties sans besoin. Rapport utilisateur : erreur lisible, action conseillée et possibilité de réessayer. Catégories minimales : dossier inaccessible, fichier instable, format inconnu, corruption, binaire absent/incompatible, timeout, échec non nul, sortie invalide, erreur transaction/BDD.

## 8. Vérification d’intégration

Avant mise en production, tests avec une version de moteur figée et documentée, et jeux de référence : coup trivial, coup ambigu, double, coup forcé, déploiement de cube, prise/passe et situation de match. Vérifier une analyse répétée identique pour le même profil, les tolérances de réponse acceptée, ainsi que l’absence de faux résultat en cas de timeout ou sortie partielle.
