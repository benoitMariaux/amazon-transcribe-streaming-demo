# Document de Spécifications

## Introduction

Ce document décrit les exigences pour l'ajout d'une interface web au projet de transcription en temps réel de France Info. L'interface permettra de visualiser le texte transcrit en temps réel tout en écoutant le flux audio de la radio directement dans le navigateur. Le backend Python (FastAPI) orchestre la capture audio via ffmpeg, l'envoi à Amazon Transcribe Streaming, et la diffusion des résultats de transcription au frontend via WebSocket. Le frontend est une page HTML/JS simple servie par le backend.

## Glossaire

- **Backend** : Serveur Python basé sur FastAPI (framework web asynchrone Python avec support natif des WebSockets) qui capture le flux audio Icecast, l'envoie à Amazon Transcribe Streaming et diffuse les résultats de transcription aux clients WebSocket connectés.
- **Frontend** : Page web HTML/JavaScript servie par le Backend, affichant le lecteur audio et la zone de transcription.
- **WebSocket_Server** : Point de terminaison WebSocket du Backend qui pousse les résultats de transcription vers le Frontend en temps réel.
- **Lecteur_Audio** : Composant HTML `<audio>` du Frontend qui lit directement le flux Icecast de France Info.
- **Zone_Transcription** : Zone de texte du Frontend où les résultats de transcription défilent en temps réel.
- **Flux_Icecast** : Flux audio HTTP de France Info (`http://icecast.radiofrance.fr/franceinfo-lofi.aac`).
- **Transcribe_Client** : Client Amazon Transcribe Streaming qui reçoit l'audio PCM et retourne les résultats de transcription (partiels et finaux).
- **Pipeline_Audio** : Processus ffmpeg qui capture le Flux_Icecast et le convertit en PCM 16kHz mono pour le Transcribe_Client.

## Exigences

### Exigence 1 : Servir l'interface web

**User Story :** En tant qu'utilisateur, je veux accéder à une interface web via mon navigateur, afin de visualiser la transcription et écouter la radio sans utiliser le terminal.

#### Critères d'acceptation

1. QUAND un utilisateur accède à l'URL racine du Backend, LE Backend DOIT servir la page Frontend (HTML/CSS/JS).
2. QUAND le Backend démarre, LE Backend DOIT afficher dans la console l'URL d'accès à l'interface web (par défaut `http://localhost:8000`).
3. SI le port configuré est déjà utilisé, ALORS LE Backend DOIT afficher un message d'erreur clair indiquant le conflit de port.

### Exigence 2 : Lecture audio en temps réel dans le navigateur

**User Story :** En tant qu'utilisateur, je veux écouter le flux radio France Info directement dans l'interface web, afin de suivre l'audio en parallèle de la transcription.

#### Critères d'acceptation

1. QUAND la page Frontend se charge, LE Lecteur_Audio DOIT afficher un lecteur audio avec les contrôles de lecture standard (play, pause, volume).
2. QUAND l'utilisateur clique sur le bouton play, LE Lecteur_Audio DOIT lire le Flux_Icecast de France Info directement depuis le navigateur.
3. SI le Flux_Icecast est indisponible, ALORS LE Frontend DOIT afficher un message d'erreur dans la zone du lecteur audio indiquant que le flux est inaccessible.

### Exigence 3 : Transcription en temps réel via WebSocket

**User Story :** En tant qu'utilisateur, je veux voir le texte transcrit apparaître en temps réel sur la page web, afin de lire ce qui est dit à la radio.

#### Critères d'acceptation

1. QUAND un client Frontend se connecte au WebSocket_Server, LE Backend DOIT démarrer le Pipeline_Audio et le Transcribe_Client si aucune session de transcription active n'existe.
2. TANT QUE la session de transcription est active, LE WebSocket_Server DOIT envoyer chaque résultat partiel du Transcribe_Client au Frontend sous forme de message JSON contenant le type (partiel ou final), le texte et un horodatage.
3. QUAND un résultat final est reçu du Transcribe_Client, LE WebSocket_Server DOIT envoyer un message JSON marqué comme final au Frontend.
4. QUAND le Frontend reçoit un résultat partiel, LA Zone_Transcription DOIT mettre à jour la ligne courante avec le texte partiel.
5. QUAND le Frontend reçoit un résultat final, LA Zone_Transcription DOIT figer la ligne courante et commencer une nouvelle ligne pour le prochain résultat.
6. SI la connexion WebSocket est perdue, ALORS LE Frontend DOIT afficher un indicateur de déconnexion et tenter une reconnexion automatique après 3 secondes.

### Exigence 4 : Gestion du cycle de vie de la transcription

**User Story :** En tant qu'utilisateur, je veux que la transcription démarre et s'arrête proprement, afin de ne pas gaspiller de ressources AWS.

#### Critères d'acceptation

1. QUAND le premier client WebSocket se connecte, LE Backend DOIT démarrer une session de transcription unique partagée entre tous les clients connectés.
2. QUAND le dernier client WebSocket se déconnecte, LE Backend DOIT arrêter le Pipeline_Audio et fermer la session Transcribe_Client après un délai de grâce de 30 secondes.
3. QUAND le Backend reçoit un signal d'arrêt (SIGINT/SIGTERM), LE Backend DOIT fermer proprement le Pipeline_Audio, la session Transcribe_Client et toutes les connexions WebSocket.
4. SI le Pipeline_Audio échoue (ffmpeg crash ou flux indisponible), ALORS LE Backend DOIT notifier tous les clients WebSocket connectés avec un message d'erreur et tenter un redémarrage automatique après 5 secondes.
5. SI le Transcribe_Client retourne une erreur, ALORS LE Backend DOIT journaliser l'erreur, notifier les clients WebSocket et tenter un redémarrage de la session de transcription.

### Exigence 5 : Format des messages WebSocket

**User Story :** En tant que développeur, je veux un format de message WebSocket structuré, afin de pouvoir traiter les données de transcription de manière fiable côté frontend.

#### Critères d'acceptation

1. LE WebSocket_Server DOIT envoyer les messages de transcription au format JSON avec les champs : `type` ("partial" ou "final"), `text` (texte transcrit) et `timestamp` (horodatage ISO 8601).
2. LE WebSocket_Server DOIT envoyer les messages d'état au format JSON avec les champs : `type` ("status"), `status` ("connected", "transcribing", "error", "reconnecting") et `message` (description lisible).
3. QUAND le Frontend reçoit un message JSON, LE Frontend DOIT valider la présence du champ `type` avant de traiter le message.
4. LE Sérialiseur_JSON DOIT encoder les messages de transcription en JSON valide.
5. LE Désérialiseur_JSON DOIT décoder les messages JSON reçus en objets de message structurés.
6. POUR TOUT message de transcription valide, sérialiser puis désérialiser DOIT produire un objet équivalent au message original (propriété aller-retour).

### Exigence 6 : Affichage fluide sans répétition

**User Story :** En tant qu'utilisateur, je veux voir le texte apparaître mot après mot de manière fluide, sans répétition, afin de lire confortablement ce qui est dit à la radio.

#### Critères d'acceptation

1. QUAND le Frontend reçoit un résultat partiel, LE Frontend DOIT calculer le diff avec le résultat partiel précédent et n'afficher que les nouveaux mots ajoutés.
2. LE Frontend NE DOIT JAMAIS afficher deux fois le même segment de texte dans la Zone_Transcription.
3. QUAND un résultat final est reçu, LE Frontend DOIT afficher les mots restants (diff entre le dernier partiel et le final), puis figer la ligne et commencer une nouvelle ligne.
4. POUR TOUT résultat partiel P(n) suivi de P(n+1) où P(n+1) commence par le même texte que P(n), LE Frontend DOIT n'ajouter que le suffixe nouveau de P(n+1).
5. SI un résultat partiel P(n+1) ne commence pas par le texte de P(n) (correction par Transcribe), LE Frontend DOIT remplacer la ligne courante entière par P(n+1) plutôt que d'accumuler du texte incohérent.

### Exigence 7 : Interface utilisateur

**User Story :** En tant qu'utilisateur, je veux une interface claire et lisible, afin de suivre confortablement la transcription en temps réel.

#### Critères d'acceptation

1. LE Frontend DOIT afficher un indicateur de statut de connexion (connecté, déconnecté, en cours de reconnexion) visible en permanence.
2. TANT QUE la Zone_Transcription contient du texte, LE Frontend DOIT défiler automatiquement vers le bas pour afficher le texte le plus récent.
3. QUAND l'utilisateur fait défiler manuellement vers le haut, LE Frontend DOIT suspendre le défilement automatique jusqu'à ce que l'utilisateur revienne en bas de la zone.
4. LE Frontend DOIT afficher un horodatage à côté de chaque ligne de transcription finale.
5. LE Frontend DOIT distinguer visuellement le texte partiel (en cours) du texte final (confirmé) par un style différent (par exemple italique pour le partiel).
