# Plan d'implémentation : Interface Web de Transcription

## Vue d'ensemble

Implémentation incrémentale d'une interface web pour la transcription en temps réel de France Info. Chaque tâche construit sur la précédente, en commençant par les modèles de données, puis le backend FastAPI, et enfin le frontend.

## Tâches

- [x] 1. Mettre en place la structure du projet et les dépendances
  - Ajouter `fastapi`, `uvicorn[standard]`, `hypothesis` et `pytest` à `requirements.txt`
  - Créer le répertoire `static/` pour le frontend
  - Créer le fichier `messages.py` avec les dataclasses `TranscriptionMessage` et `StatusMessage`, ainsi que les fonctions `serialize` et `deserialize`
  - _Requirements: 5.1, 5.2, 5.4, 5.5_

- [ ] 2. Tests des modèles de messages
  - [x] 2.1 Écrire les tests unitaires pour `messages.py`
    - Tester la sérialisation d'un message de transcription partiel et final
    - Tester la sérialisation d'un message de statut
    - Tester la désérialisation d'un JSON sans champ `type` (doit lever une erreur)
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 2.2 Écrire le test de propriété pour l'aller-retour de sérialisation
    - **Property 1 : Aller-retour de sérialisation des messages**
    - **Validates: Requirements 5.4, 5.5, 5.6**

  - [ ]* 2.3 Écrire le test de propriété pour la structure des messages de transcription
    - **Property 2 : Structure des messages de transcription**
    - **Validates: Requirements 3.2, 3.3, 5.1**

  - [ ]* 2.4 Écrire le test de propriété pour la structure des messages de statut
    - **Property 3 : Structure des messages de statut**
    - **Validates: Requirements 5.2**

  - [ ]* 2.5 Écrire le test de propriété pour le rejet des messages sans type
    - **Property 4 : Validation des messages — rejet sans champ type**
    - **Validates: Requirements 5.3**

- [x] 3. Checkpoint — Vérifier que tous les tests passent
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implémenter la session de transcription
  - Créer `transcription_session.py` avec la classe `TranscriptionSession`
  - Implémenter `_start_ffmpeg()` pour lancer ffmpeg (réutiliser la logique de `transcribe_streaming.py`)
  - Implémenter `start()` et `stop()` pour gérer le cycle de vie du pipeline audio et du client Transcribe
  - Implémenter `_handle_transcript_event()` pour convertir les événements Transcribe en `TranscriptionMessage` et appeler le callback `on_message`
  - Implémenter la gestion des erreurs : redémarrage automatique après 5 secondes si ffmpeg ou Transcribe échoue
  - _Requirements: 3.1, 3.2, 3.3, 4.4, 4.5_

- [x] 5. Implémenter le gestionnaire de sessions
  - Créer `session_manager.py` avec la classe `SessionManager`
  - Implémenter `connect()` : ajouter le client, démarrer la transcription si premier client, annuler le délai de grâce si en cours
  - Implémenter `disconnect()` : retirer le client, planifier l'arrêt avec délai de grâce de 30 secondes si dernier client
  - Implémenter `broadcast()` : envoyer un message JSON à tous les clients connectés
  - _Requirements: 4.1, 4.2, 4.4, 4.5_

  - [ ]* 5.1 Écrire le test de propriété pour l'unicité de session
    - **Property 5 : Unicité de la session de transcription**
    - **Validates: Requirements 4.1**

  - [ ]* 5.2 Écrire le test de propriété pour la diffusion des erreurs
    - **Property 6 : Diffusion des erreurs à tous les clients**
    - **Validates: Requirements 4.4, 4.5**

- [x] 6. Implémenter le serveur FastAPI
  - Créer `app.py` avec l'application FastAPI
  - Implémenter la route GET `/` qui sert `static/index.html`
  - Implémenter l'endpoint WebSocket `/ws` qui délègue au `SessionManager`
  - Implémenter la gestion du cycle de vie (startup/shutdown) pour l'arrêt propre sur SIGINT/SIGTERM
  - Afficher l'URL d'accès dans la console au démarrage
  - Écouter sur `127.0.0.1` uniquement (pas d'accès externe)
  - _Requirements: 1.1, 1.2, 1.3, 4.3_

- [x] 7. Checkpoint — Vérifier que le backend fonctionne
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Créer le frontend
  - Créer `static/index.html` avec HTML, CSS et JavaScript intégrés
  - Implémenter le lecteur audio `<audio>` pointant sur le flux Icecast avec contrôles standard
  - Implémenter l'indicateur de statut de connexion (connecté/déconnecté/reconnexion)
  - Implémenter la connexion WebSocket avec reconnexion automatique après 3 secondes
  - Implémenter l'algorithme de diff incrémental : maintenir `lastPartialText`, calculer le suffixe nouveau pour chaque partiel, remplacer la ligne entière si Transcribe corrige (le nouveau partiel ne commence pas par l'ancien)
  - Implémenter le traitement des messages JSON : affichage mot après mot sans répétition pour les partiels, ajout des lignes finales (avec horodatage)
  - Implémenter le défilement automatique avec suspension quand l'utilisateur scrolle vers le haut
  - _Requirements: 2.1, 2.2, 2.3, 3.4, 3.5, 3.6, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 8.1 Écrire le test de propriété pour l'horodatage dans le rendu
    - **Property 7 : Horodatage dans le rendu des lignes finales**
    - **Validates: Requirements 7.4**

  - [ ]* 8.2 Écrire le test de propriété pour l'affichage incrémental sans répétition
    - **Property 8 : Affichage incrémental sans répétition**
    - **Validates: Requirements 6.1, 6.2, 6.4**

- [x] 9. Intégration et câblage final
  - Connecter le `SessionManager` à l'application FastAPI dans `app.py`
  - Vérifier que la `TranscriptionSession` utilise le callback `broadcast` du `SessionManager`
  - Mettre à jour `requirements.txt` avec toutes les dépendances finales
  - _Requirements: 1.1, 3.1, 4.1_

- [x] 10. Checkpoint final — Vérifier que tout fonctionne
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Les tâches marquées avec `*` sont optionnelles et peuvent être ignorées pour un MVP plus rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les checkpoints permettent une validation incrémentale
- Le backend écoute sur `127.0.0.1` uniquement — aucune ressource AWS publique n'est créée
- Les credentials AWS existantes sont réutilisées (même configuration que le projet CLI actuel)
