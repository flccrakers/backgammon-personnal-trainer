# 05 — Interface PyQt

> **État réel** : l'interface implémentée (sessions d'entraînement verrouillées, statistiques gnubg, flèches colorées, dés dessinés, fichier unique avec session automatique) est décrite dans `07-etat-implementation.md`, qui prévaut sur ce document.

## 1. Principes d’interface

- Interface PyQt dédiée à la présentation et à la saisie; les services moteur/base restent indépendants.
- Les imports, analyses et requêtes longues s’exécutent hors du fil UI. Afficher progression, annulation lorsque sûre, et résultats partiels clairement qualifiés.
- Un écran doit distinguer les exercices disponibles, les fichiers non analysés et les fichiers sans erreur détectée.
- Présenter clairement le joueur au trait, l’orientation du plateau, les dés, le type d’exercice et le contexte disponible.

## 2. Écrans et navigation

1. **Accueil** : accès à l’entraînement global, choix d’un fichier unique, scan/import et paramètres.
2. **Import/scan** : dossier actif, progression et résultat par fichier; possibilité de relancer les échecs et d’ouvrir un diagnostic.
3. **Liste d’exercices** : filtres mouvement/cube, source/match, statut d’entraînement; mode unique avec filtre non modifiable sur le fichier sélectionné.
4. **Exercice** : plateau et panneau d’action, retour/validation/correction, précédent/suivant et quitter.
5. **Configuration** : chemins, options de scan/moteur et validation des paramètres.

## 3. Écran mouvement

### Informations affichées

- plateau et orientation, deux couleurs/joueurs, joueur actif;
- jet de dés (dés séparés; indication explicite des doubles);
- contexte de match disponible, sans encombrer l’exercice;
- consigne et état de tentative.

### Saisie

Le choix d’interaction doit permettre de sélectionner une origine puis une destination, ou de faire glisser un pion, avec retour accessible équivalent. Les coups composés sont présentés comme une suite d’actions; chaque déplacement est validé au regard des règles et du jet restant. Gérer les sorties de pions, coups forcés, doubles et ordre alternatif de dés. Ne pas supposer qu’une seule représentation textuelle correspond à un coup.

La validation transmet une réponse normalisée au service. Le service effectue la comparaison autoritative; le widget ne décide pas seul qu’un coup est juste.

### Résultat et flèches

- Réponse correcte : message de succès, conserver le plateau joué et proposer « exercice suivant ».
- Réponse incorrecte : signalement sans pénalité implicite, possibilité de réessayer ou de révéler la solution selon la politique produit.
- À la révélation/correction, représenter chaque déplacement de référence par une flèche origine → destination avec flèches distinctes/couleurs accessibles et une liste textuelle équivalente.
- Pour plusieurs réponses acceptables, signaler que la réponse appartient aux alternatives optimales; ne pas marquer incorrect une ligne équivalente.
- Les flèches ne doivent pas se confondre avec les flèches de sens de jeu ou de sélection. Fournir légende/contraste et possibilité de masquer/réafficher.

## 4. Écran cube

Afficher position, propriétaire/valeur du cube, score et longueur de match lorsque disponibles, puis les actions licites pour l’état courant. Les libellés doivent être contextualisés (par exemple offrir/refuser un double, prendre/passer) plutôt que des boutons génériques. Après validation, expliquer l’action de référence et, le cas échéant, la réponse après double. Ne pas proposer d’action de cube illégale.

## 5. Validation et progression

- Le bouton de validation reste désactivé tant que la réponse est incomplète/illégale ou affiche précisément ce qui manque.
- Après chaque tentative, mettre à jour le nombre de tentatives et l’état `in_progress`, `correct` ou `skipped` via le service.
- Après une réponse correcte, ne pas modifier la position canonique source; l’état de l’exercice est séparé.
- Le changement d’exercice demande confirmation uniquement si une saisie non validée serait perdue.
- La navigation affiche compteur (ex. 3/12) et filtre actif; fin de liste fournit une action claire pour recommencer, changer de filtre ou quitter.
- Si aucun exercice : distinguer « aucun coup/décision classé Très mauvais par gnubg », import en attente, erreur d’analyse, et fichier invalide.

## 6. Mode fichier unique

Le sélecteur accepte un fichier `.mat`. Une fois le fichier sélectionné :

- afficher son nom et son état d’import/empreinte;
- lancer le traitement requis via worker si nécessaire;
- charger les exercices dont la source correspond uniquement à ce fichier;
- maintenir ce filtre pendant la navigation et la relance;
- signaler un fichier modifié depuis la dernière analyse et proposer l’actualisation;
- quitter explicitement ce mode pour revenir à l’entraînement général.

## 7. État asynchrone et erreurs

Les workers publient des états typés : démarrage, progression, terminé avec rapport, annulation, échec récupérable/fatal. Les signaux sont reçus sur le fil UI et ne transportent pas de connexion SQL ou objet mutable partagé. Éviter le gel du plateau durant le moteur; rendre l’annulation honnête (si le sous-processus ne peut être arrêté proprement, afficher qu’il termine/annule).

Messages utilisateur en français et actionnables; journal technique séparé. Ne pas afficher une correction si l’analyse est absente/incomplète. Une erreur du moteur propose de réessayer ou consulter les paramètres, plutôt que « aucune erreur trouvée ».

## 8. Accessibilité et tests d’acceptation UI

- Contraste suffisant, symboles non fondés uniquement sur la couleur, navigation clavier et libellés accessibles.
- Toutes les informations d’une flèche sont aussi disponibles sous forme textuelle.
- Vérifier scénarios mouvement correct/incorrect/illégal, réponse équivalente, double, sortie, cube take/pass, saut, fin de série, erreur moteur et mode fichier unique.
- Automatiser les interactions UI avec services simulés; vérifier séparément la vérité de la validation dans les tests de service.
