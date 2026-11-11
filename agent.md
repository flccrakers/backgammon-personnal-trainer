# Instructions pour l’agent développeur

## Rôle

Tu es l’agent chargé de concevoir et réaliser, par étapes, un entraîneur local de backgammon à partir de parties `.mat`. Respecte l’architecture, les contrats et les critères documentés dans ce dossier. Privilégie l’exactitude des positions et des décisions à la quantité d’exercices produite.

## Objectifs produit

- Importer automatiquement ou sur demande les fichiers `.mat` présents dans un répertoire configurable.
- Identifier uniquement les coups de déplacement et décisions de cube classés **« Très mauvais » (`very bad`)** par GNU Backgammon (`gnubg`).
- Stocker les éléments nécessaires pour comprendre et rejouer chaque erreur.
- Fournir des exercices interactifs avec saisie, validation, correction visuelle par flèches et navigation.
- Permettre un mode limité à un seul fichier `.mat`, ne proposant que les exercices issus du match correspondant.
- Séparer le moteur Python, la persistance et l’interface PyQt; rendre l’API moteur appelable sans GUI.

## Contraintes non négociables

1. **Ne pas confondre GnuPG et GNU Backgammon.** Le besoin cite « gnupg », mais `gpg` sert au chiffrement. Avant tout appel externe, confirmer que le moteur attendu est GNU Backgammon (`gnubg`) et documenter le binaire/version. Si la clarification est impossible, bloquer la partie d’intégration et demander décision; ne pas choisir silencieusement un outil.
2. **Respecter le format `.mat` observé.** La référence actuelle est un export texte ASCII BackgammonGalaxy : en-têtes `;`, blocs `Game N`, scores, tours numérotés à deux côtés, dés, coups départ/arrivée, actions de cube et résultat. Le fichier ne contient aucune évaluation gnubg. Tester les variantes et fichiers invalides avec des fixtures; ne pas inventer d’extensions au format.
3. **Ne pas assimiler une suggestion du moteur à une vérité absolue.** Conserver la méthode et version d’analyse, la métrique diagnostique, la classification et la ligne de référence. Signaler dans l’interface qu’il s’agit d’une analyse selon ces paramètres.
4. Ne pas exécuter le binaire via un shell construit avec des chaînes non fiables. Utiliser un lancement de processus à arguments séparés, avec délais, limites de sortie et traitement sûr des chemins.
5. Le mode fichier unique filtre strictement sur le match sélectionné; ne pas mélanger des exercices d’autres parties.
6. Le code GUI n’accède pas aux tables directement et n’effectue pas d’analyse synchroniquement sur le fil d’affichage.
7. Les imports doivent être idempotents, transactionnels par partie, reprenables après erreur et sans effacer les corrections/état d’entraînement.
8. Les positions, joueurs, couleurs, orientation du plateau et coups doivent utiliser une convention canonique documentée et testée.

## Workflow de développement

Pour chaque tranche verticale :

1. Lire les documents pertinents et consigner les hypothèses non résolues.
2. Définir le contrat de l’entrée/sortie et les cas d’échec avant l’implémentation.
3. Créer une fixture minimale, réaliste et anonymisée; ne pas modifier la source utilisateur.
4. Implémenter d’abord le modèle métier ou adaptateur testable sans PyQt.
5. Ajouter des tests unitaires de normalisation, règles métier, unicité et erreurs; ajouter tests d’intégration pour le parseur et le binaire seulement si disponibles.
6. Passer les tests, vérifier une importation répétée, un fichier modifié, un fichier tronqué et une reprise après interruption.
7. Exposer la capacité via l’API publique puis la brancher à la GUI par tâches asynchrones.
8. Mettre à jour les docs lorsque le format, une décision d’analyse ou un contrat change.

Ordre conseillé : validation moteur/format → modèle canonique → schéma et migrations → import idempotent → analyse et sélection d’erreurs → API de service → GUI → tests d’acceptation et packaging.

## Conventions de conception

- Python typé et découpé en modules par responsabilité; fonctions métier déterministes isolées des entrées/sorties.
- Utiliser des migrations versionnées, jamais une modification silencieuse de schéma au démarrage.
- Persister les valeurs canoniques (positions et dés structurés), pas seulement le texte affiché.
- Distinguer l’identité du fichier, l’identité de la partie et l’identité de la décision.
- Ne pas filtrer les exercices par seuil numérique : seuls les mouvements et décisions de cube classés `very bad` par `gnubg` sont retenus. Une perte d’équité peut être conservée comme information de diagnostic, pas comme critère d’inclusion.
- Les erreurs de processus externe doivent conserver code retour et diagnostic expurgé; ne pas masquer un échec sous une analyse vide.
- La configuration est validée au démarrage et ses valeurs effectives sont consultables sans divulguer de secrets.
- Tout texte utilisateur/fichier est considéré comme donnée non fiable. Échapper les textes d’affichage et limiter les chemins autorisés si une politique de sécurité est mise en place.

## Critères de complétion

Une fonctionnalité est achevée si :

- elle est couverte par des tests reproductibles;
- les critères d’acceptation correspondants de `01-specifications-fonctionnelles.md` passent;
- l’import répété ne crée pas de doublons et les échecs sont visibles/reprenables;
- aucune opération lourde ne bloque PyQt;
- les docs reflètent les contrats implémentés et les limitations connues;
- le binaire requis et ses versions sont vérifiés explicitement, et aucun comportement n’est basé sur une hypothèse non signalée.

## Questions à escalader, pas à trancher implicitement

- « gnupg » désigne-t-il GNU Backgammon (`gnubg`) ou un autre moteur ?
- Quelles variantes/version du format ASCII BackgammonGalaxy doivent être prises en charge au-delà de la structure observée ?
- Quelle profondeur/niveau d’analyse de `gnubg` faut-il utiliser ? Le critère d’inclusion est fixé à `very bad`.
- Inclut-on les décisions de cube dépendant du score, du match, du gammons/backgammons et du match equity table ?
- Le chemin BDD par défaut doit-il être global à l’utilisateur ou relatif au profil du projet ?
