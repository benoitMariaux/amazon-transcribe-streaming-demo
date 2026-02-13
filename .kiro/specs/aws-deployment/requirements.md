# Document d'Exigences — Déploiement AWS

## Introduction

Ce document décrit les exigences pour le déploiement de l'application web de transcription en temps réel de France Info sur AWS, en utilisant AWS CDK (Python). L'architecture cible sépare le frontend statique (S3 + CloudFront) du backend (ECS Fargate derrière un ALB), avec CloudFront comme point d'entrée unique routant les requêtes statiques vers S3 et les connexions WebSocket vers le backend.

## Glossaire

- **CDK_Stack** : Le stack AWS CDK Python qui définit l'ensemble de l'infrastructure
- **S3_Bucket** : Le bucket Amazon S3 hébergeant les fichiers statiques du frontend
- **CloudFront_Distribution** : La distribution Amazon CloudFront servant de point d'entrée unique
- **OAC** : Origin Access Control, mécanisme permettant à CloudFront d'accéder au bucket S3 privé
- **VPC** : Le Virtual Private Cloud contenant les ressources réseau
- **ECS_Service** : Le service AWS ECS Fargate exécutant le conteneur backend
- **ALB** : L'Application Load Balancer interne routant le trafic vers ECS Fargate
- **Task_Definition** : La définition de tâche ECS décrivant le conteneur Docker (Python + ffmpeg)
- **IAM_Role** : Le rôle IAM attribué à la tâche ECS pour accéder à Amazon Transcribe
- **Security_Group** : Les groupes de sécurité contrôlant le trafic réseau
- **Dockerfile** : Le fichier de construction de l'image Docker pour le backend

## Exigences

### Exigence 1 : Infrastructure réseau (VPC)

**User Story :** En tant qu'opérateur, je veux une infrastructure réseau isolée, afin que les ressources backend soient protégées du trafic externe direct.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer un VPC avec des sous-réseaux privés et des sous-réseaux publics
2. THE CDK_Stack SHALL placer les tâches ECS Fargate exclusivement dans les sous-réseaux privés
3. THE CDK_Stack SHALL configurer un NAT Gateway pour permettre aux tâches ECS d'accéder à Internet (flux Icecast, Transcribe API)
4. THE CDK_Stack SHALL configurer le VPC dans la région us-east-1

### Exigence 2 : Hébergement du frontend statique (S3)

**User Story :** En tant qu'opérateur, je veux héberger le frontend dans un bucket S3 privé, afin que les fichiers statiques soient servis de manière sécurisée via CloudFront uniquement.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer un S3_Bucket avec `block_public_access` configuré à `BLOCK_ALL`
2. THE CDK_Stack SHALL configurer le S3_Bucket avec `public_read_access` à `False`
3. THE CDK_Stack SHALL configurer le S3_Bucket avec le chiffrement `S3_MANAGED`
4. THE CDK_Stack SHALL déployer le fichier `index.html` dans le S3_Bucket via un `BucketDeployment`
5. IF un accès direct au S3_Bucket est tenté sans passer par CloudFront, THEN le S3_Bucket SHALL refuser la requête

### Exigence 3 : Distribution CloudFront

**User Story :** En tant qu'utilisateur, je veux accéder à l'application via un point d'entrée unique CloudFront, afin de bénéficier d'une expérience fluide avec le frontend et le backend accessibles depuis la même URL.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer une CloudFront_Distribution avec un comportement par défaut pointant vers le S3_Bucket via un OAC
2. THE CDK_Stack SHALL configurer un comportement additionnel sur le chemin `/ws` pointant vers l'ALB comme origine
3. WHEN une requête arrive sur le chemin `/ws`, THEN la CloudFront_Distribution SHALL router la requête vers l'ALB avec le support WebSocket activé
4. WHEN une requête arrive sur tout autre chemin, THEN la CloudFront_Distribution SHALL servir le contenu depuis le S3_Bucket
5. THE CDK_Stack SHALL configurer le comportement `/ws` avec la politique de cache `CACHING_DISABLED` et la politique `ALL_VIEWER` pour les en-têtes d'origine
6. THE CDK_Stack SHALL configurer le document d'erreur par défaut sur `index.html` pour le comportement par défaut

### Exigence 4 : Backend conteneurisé (ECS Fargate)

**User Story :** En tant qu'opérateur, je veux exécuter le backend FastAPI dans un conteneur ECS Fargate, afin que l'application soit scalable et managée sans gérer de serveurs.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer un Dockerfile installant Python, ffmpeg, et les dépendances de l'application
2. THE CDK_Stack SHALL créer une Task_Definition Fargate avec les ressources CPU et mémoire appropriées
3. THE CDK_Stack SHALL créer un ECS_Service exécutant la Task_Definition dans les sous-réseaux privés du VPC
4. WHEN le conteneur démarre, THEN le ECS_Service SHALL exécuter le serveur FastAPI sur le port 8000
5. THE CDK_Stack SHALL configurer le health check de l'ALB sur le endpoint HTTP du backend

### Exigence 5 : Load Balancer interne (ALB)

**User Story :** En tant qu'opérateur, je veux un ALB interne devant ECS Fargate, afin que CloudFront puisse router le trafic WebSocket vers le backend sans exposer le backend directement sur Internet.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer un ALB interne (non exposé sur Internet) dans le VPC
2. THE CDK_Stack SHALL configurer un listener HTTP sur le port 80 de l'ALB
3. THE CDK_Stack SHALL configurer un target group pointant vers le ECS_Service sur le port 8000
4. THE CDK_Stack SHALL activer le support des connexions WebSocket (stickiness) sur le target group
5. IF un accès direct à l'ALB est tenté depuis Internet, THEN l'ALB SHALL refuser la connexion car il est interne au VPC

### Exigence 6 : Permissions IAM

**User Story :** En tant qu'opérateur, je veux des permissions IAM minimales pour la tâche ECS, afin de respecter le principe du moindre privilège.

#### Critères d'acceptation

1. THE CDK_Stack SHALL créer un IAM_Role pour la Task_Definition avec la permission `transcribe:StartStreamTranscription`
2. THE CDK_Stack SHALL limiter les permissions IAM au strict minimum requis pour le fonctionnement de l'application
3. THE IAM_Role SHALL utiliser le service principal `ecs-tasks.amazonaws.com` comme entité de confiance

### Exigence 7 : Sécurité réseau (Security Groups)

**User Story :** En tant qu'opérateur, je veux des groupes de sécurité restrictifs, afin que le trafic réseau soit limité au strict nécessaire.

#### Critères d'acceptation

1. THE CDK_Stack SHALL configurer le Security_Group de l'ALB pour accepter le trafic entrant uniquement sur le port 80
2. THE CDK_Stack SHALL configurer le Security_Group du ECS_Service pour accepter le trafic entrant uniquement depuis le Security_Group de l'ALB sur le port 8000
3. THE CDK_Stack SHALL interdire tout trafic entrant direct depuis `0.0.0.0/0` vers le ECS_Service

### Exigence 8 : Adaptation du frontend pour le déploiement

**User Story :** En tant qu'utilisateur, je veux que le frontend fonctionne correctement une fois déployé sur CloudFront, afin que la connexion WebSocket s'établisse automatiquement vers le bon endpoint.

#### Critères d'acceptation

1. WHEN le frontend est servi via CloudFront, THEN le frontend SHALL construire l'URL WebSocket en utilisant `wss://` et `window.location.host` pour se connecter au chemin `/ws`
2. THE frontend SHALL fonctionner sans modification de l'URL WebSocket grâce au routage CloudFront unifié

### Exigence 9 : Dockerfile du backend

**User Story :** En tant qu'opérateur, je veux un Dockerfile fonctionnel pour le backend, afin que l'image puisse être construite et déployée sur ECS Fargate.

#### Critères d'acceptation

1. THE Dockerfile SHALL utiliser une image de base Python compatible avec les dépendances de l'application
2. THE Dockerfile SHALL installer ffmpeg comme dépendance système
3. THE Dockerfile SHALL installer les dépendances Python depuis `requirements.txt`
4. THE Dockerfile SHALL copier les fichiers source de l'application (app.py, messages.py, session_manager.py, transcription_session.py)
5. THE Dockerfile SHALL exposer le port 8000
6. WHEN le conteneur démarre, THEN le Dockerfile SHALL exécuter uvicorn avec le host `0.0.0.0` et le port `8000`
7. THE Dockerfile SHALL exclure les fichiers non nécessaires au runtime via un `.dockerignore`

### Exigence 10 : Outputs du stack CDK

**User Story :** En tant qu'opérateur, je veux que le stack CDK affiche les URLs de déploiement, afin de pouvoir accéder facilement à l'application après le déploiement.

#### Critères d'acceptation

1. THE CDK_Stack SHALL afficher l'URL de la CloudFront_Distribution en sortie du déploiement
2. THE CDK_Stack SHALL afficher le nom du S3_Bucket en sortie du déploiement
