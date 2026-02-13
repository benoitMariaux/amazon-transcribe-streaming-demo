# Amazon Transcribe — Transcription en direct de France Info

Application web qui transcrit en temps réel le flux audio de France Info grâce à Amazon Transcribe Streaming. L'interface affiche la transcription au fil de l'eau avec un lecteur audio intégré.

## Architecture

```
Navigateur (HTTPS/WSS)
    │
    ▼
CloudFront
    ├── /* ──► S3 (frontend HTML via OAC)
    └── /ws ──► ALB ──► ECS Fargate (backend Python)
                              │
                              ├── WebSocket vers les clients
                              ├── Flux audio France Info (icecast)
                              └── Amazon Transcribe Streaming
```

- S3 : bucket privé (BlockPublicAccess.BLOCK_ALL), accès via CloudFront OAC uniquement
- ALB : internet-facing mais SG restreint au CloudFront managed prefix list
- ECS Fargate : subnets privés, permission IAM minimale (transcribe:StartStreamTranscription)
- Pas de secret, pas de credentials dans le code

## Prérequis

- Compte AWS avec accès à Amazon Transcribe (région us-east-1)
- AWS CLI configuré (`aws configure`)
- Python 3.11+
- Node.js + CDK CLI (`npm install -g aws-cdk`)
- ffmpeg (pour le développement local uniquement)

## Déploiement rapide

```bash
./deploy.sh
```

Ce script :
1. Déploie le stack CDK (VPC, ECS, ALB, CloudFront, S3, ECR)
2. Build l'image Docker via AWS CodeBuild (pas besoin de Docker en local)
3. Force un nouveau déploiement ECS
4. Affiche l'URL CloudFront

## Déploiement manuel

```bash
# 1. Installer les dépendances CDK
cd infra && pip install -r requirements.txt && cd ..

# 2. Déployer le stack
cd infra && cdk deploy --app "python app.py" && cd ..

# 3. Builder l'image Docker via CodeBuild (voir deploy.sh pour les détails)

# 4. Forcer le redéploiement ECS
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

## Développement local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
# Ouvrir http://localhost:8000
```

## Structure du projet

```
├── app.py                      # Serveur FastAPI (WebSocket + frontend)
├── transcription_session.py    # Session de transcription Amazon Transcribe
├── session_manager.py          # Gestion des connexions WebSocket
├── messages.py                 # Sérialisation des messages JSON
├── static/index.html           # Interface web
├── Dockerfile                  # Image Docker pour ECS
├── buildspec.yml               # Build CodeBuild (variables d'environnement)
├── deploy.sh                   # Script de déploiement complet
├── infra/
│   ├── app.py                  # Point d'entrée CDK
│   ├── transcription_stack.py  # Stack CDK (VPC, ECS, ALB, CloudFront, S3)
│   ├── cdk.json                # Configuration CDK
│   └── requirements.txt        # Dépendances CDK
└── tests/                      # Tests unitaires
```

## Nettoyage

```bash
cd infra && cdk destroy --app "python app.py" && cd ..
```

## Scripts CLI (hors web)

Pour tester la transcription en ligne de commande sans l'interface web :

```bash
# Valider le flux audio
python audio_stream_validator.py

# Transcription streaming dans le terminal
python transcribe_streaming_clean.py
```
