# Plan d'implémentation : Déploiement AWS

## Vue d'ensemble

Implémentation incrémentale de l'infrastructure CDK Python pour déployer l'application de transcription sur AWS. Chaque tâche construit sur la précédente, en commençant par le Dockerfile et la structure CDK, puis les composants d'infrastructure, et enfin le câblage CloudFront.

## Tâches

- [x] 1. Créer le Dockerfile et le .dockerignore
  - Créer le `Dockerfile` à la racine du projet avec Python 3.13-slim, ffmpeg, les dépendances pip, et les fichiers source
  - Créer le `.dockerignore` excluant venv, __pycache__, .git, tests, static, infra, .kiro
  - Le CMD doit exécuter `uvicorn app:app --host 0.0.0.0 --port 8000`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 2. Initialiser le projet CDK et le stack de base
  - [x] 2.1 Créer la structure `infra/` avec `app.py`, `transcription_stack.py`, `requirements.txt`, et `cdk.json`
    - `infra/requirements.txt` doit contenir `aws-cdk-lib>=2.150.0`, `constructs>=10.0.0`
    - `infra/cdk.json` doit pointer vers `python infra/app.py` comme commande app
    - `infra/app.py` instancie le stack avec `env=cdk.Environment(region="us-east-1")`
    - `infra/transcription_stack.py` définit la classe `TranscriptionAppStack` vide
    - _Requirements: 1.4, 10.1, 10.2_

- [x] 3. Implémenter le VPC et le bucket S3
  - [x] 3.1 Ajouter le VPC au stack
    - VPC avec 2 AZ, 1 NAT Gateway, sous-réseaux publics et privés (PRIVATE_WITH_EGRESS)
    - _Requirements: 1.1, 1.3_
  - [x] 3.2 Ajouter le bucket S3 frontend au stack
    - `block_public_access=BLOCK_ALL`, `public_read_access=False`, `encryption=S3_MANAGED`
    - `removal_policy=DESTROY`, `auto_delete_objects=True`
    - Ajouter un `BucketDeployment` depuis `./static`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [ ]* 3.3 Écrire le test de propriété pour les buckets S3
    - **Property 1 : Tous les buckets S3 bloquent l'accès public**
    - **Validates: Requirements 2.1, 2.2, 2.5**

- [x] 4. Implémenter ECS Fargate et l'ALB interne
  - [x] 4.1 Ajouter le cluster ECS, la task definition, et le service Fargate
    - Cluster ECS dans le VPC
    - Task definition Fargate (256 CPU, 512 MiB mémoire)
    - Image Docker via `ContainerImage.from_asset(".")` pointant vers la racine du projet
    - Port mapping sur 8000, logs CloudWatch
    - Service Fargate dans les sous-réseaux privés
    - Ajouter la permission `transcribe:StartStreamTranscription` au rôle de tâche
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.1, 6.2, 6.3_
  - [x] 4.2 Ajouter l'ALB interne et le target group
    - ALB `internet_facing=False` dans les sous-réseaux privés
    - Listener HTTP port 80
    - Target group vers le service ECS sur le port 8000
    - Health check sur `/` avec code 200
    - Stickiness activée pour WebSocket
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x] 4.3 Configurer les security groups
    - SG de l'ALB : ingress depuis le VPC CIDR sur le port 80
    - SG du service ECS : ingress uniquement depuis le SG de l'ALB sur le port 8000
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ]* 4.4 Écrire les tests de propriétés pour ECS et ALB
    - **Property 2 : Tous les services ECS tournent dans des sous-réseaux privés**
    - **Validates: Requirements 1.2, 4.3**
    - **Property 3 : Tous les load balancers sont internes**
    - **Validates: Requirements 5.1, 5.5**
    - **Property 4 : Aucun security group ECS n'autorise l'ingress depuis 0.0.0.0/0**
    - **Validates: Requirements 7.3**
    - **Property 5 : Les politiques IAM respectent le moindre privilège**
    - **Validates: Requirements 6.2**

- [x] 5. Checkpoint — Vérifier la synthèse CDK
  - Exécuter `cdk synth` pour vérifier que le template se génère sans erreur
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implémenter CloudFront et câbler les origines
  - [x] 6.1 Ajouter la distribution CloudFront avec OAC et routage /ws
    - Créer un OAC (S3OriginAccessControl) pour l'accès au bucket S3
    - Comportement par défaut : origine S3 via OAC, redirect HTTPS
    - Comportement `/ws` : origine ALB, cache désactivé, `ALL_VIEWER` origin request policy, `ALLOW_ALL` methods
    - Document racine par défaut : `index.html`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 2.5_
  - [x] 6.2 Ajouter les CfnOutput pour l'URL CloudFront et le nom du bucket
    - _Requirements: 10.1, 10.2_
  - [ ]* 6.3 Écrire les tests unitaires pour la configuration CloudFront
    - Vérifier la présence de l'OAC
    - Vérifier le comportement par défaut vers S3
    - Vérifier le comportement `/ws` vers l'ALB avec cache désactivé
    - Vérifier les outputs
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 10.1, 10.2_

- [x] 7. Adapter le backend pour le déploiement
  - Modifier `app.py` pour que le host soit configurable via variable d'environnement (défaut `0.0.0.0` en production, `127.0.0.1` en local)
  - Vérifier que le frontend utilise déjà `window.location.host` pour l'URL WebSocket (pas de modification nécessaire)
  - _Requirements: 8.1, 8.2, 4.4_

- [x] 8. Checkpoint final — Vérifier tous les tests et la synthèse
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriétés valident les invariants de sécurité universels sur le template CloudFormation
- Les tests unitaires valident des exemples spécifiques de configuration
- La bibliothèque hypothesis est utilisée pour les tests de propriétés
