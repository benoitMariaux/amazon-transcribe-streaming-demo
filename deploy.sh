#!/bin/bash
# Script de deploiement complet pour la demo de transcription en direct.
# Usage: ./deploy.sh
#
# Pre-requis:
#   - AWS CLI configure (credentials + region us-east-1)
#   - Python 3.11+ avec venv
#   - Node.js (pour CDK CLI)
#   - CDK CLI: npm install -g aws-cdk
#
# Ce script:
#   1. Deploie le stack CDK (VPC, ECS, ALB, CloudFront, S3, ECR)
#   2. Build l'image Docker via CodeBuild (pas besoin de Docker local)
#   3. Force un nouveau deploiement ECS pour utiliser la derniere image
#   4. Affiche l'URL CloudFront

set -euo pipefail

REGION="us-east-1"
STACK_NAME="TranscriptionAppStack"
ECR_REPO="transcription-app"
CODEBUILD_PROJECT="transcription-app-build"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=== Deploiement de la demo de transcription ==="
echo "Compte: $ACCOUNT_ID | Region: $REGION"
echo ""

# --- Etape 1: CDK Deploy ---
echo "[1/4] Deploiement du stack CDK..."
cd infra
pip install -r requirements.txt -q
cdk deploy --app "python app.py" --require-approval never
cd ..

# --- Etape 2: Creer le projet CodeBuild (si absent) ---
echo ""
echo "[2/4] Configuration de CodeBuild..."

if ! aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$CODEBUILD_PROJECT"; then
    echo "  Creation du role IAM pour CodeBuild..."
    ROLE_NAME="codebuild-transcription-role"

    cat > /tmp/cb-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "codebuild.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

    aws iam create-role --role-name "$ROLE_NAME" \
        --assume-role-policy-document file:///tmp/cb-trust.json \
        --query 'Role.Arn' --output text 2>/dev/null || true

    cat > /tmp/cb-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:GetObjectVersion"],
      "Resource": "arn:aws:s3:::codebuild-transcription-source-${ACCOUNT_ID}/*"
    }
  ]
}
EOF

    aws iam put-role-policy --role-name "$ROLE_NAME" \
        --policy-name codebuild-ecr-policy \
        --policy-document file:///tmp/cb-policy.json 2>/dev/null || true

    echo "  Creation du projet CodeBuild..."
    sleep 10  # Attendre propagation IAM

    aws codebuild create-project \
        --name "$CODEBUILD_PROJECT" \
        --source '{"type":"S3","location":"codebuild-transcription-source-'$ACCOUNT_ID'/source.zip"}' \
        --artifacts '{"type":"NO_ARTIFACTS"}' \
        --environment '{
            "type":"LINUX_CONTAINER",
            "image":"aws/codebuild/standard:7.0",
            "computeType":"BUILD_GENERAL1_SMALL",
            "privilegedMode":true,
            "environmentVariables":[
                {"name":"AWS_DEFAULT_REGION","value":"'$REGION'","type":"PLAINTEXT"},
                {"name":"AWS_ACCOUNT_ID","value":"'$ACCOUNT_ID'","type":"PLAINTEXT"},
                {"name":"IMAGE_REPO_NAME","value":"'$ECR_REPO'","type":"PLAINTEXT"},
                {"name":"IMAGE_TAG","value":"latest","type":"PLAINTEXT"}
            ]
        }' \
        --service-role "arn:aws:iam::${ACCOUNT_ID}:role/$ROLE_NAME" \
        --query 'project.name' --output text
else
    echo "  Projet CodeBuild deja existant."
fi

# --- Etape 3: Build Docker via CodeBuild ---
echo ""
echo "[3/4] Build de l'image Docker via CodeBuild..."

# Creer le bucket source S3 si absent
SOURCE_BUCKET="codebuild-transcription-source-${ACCOUNT_ID}"
aws s3api create-bucket --bucket "$SOURCE_BUCKET" \
    --region "$REGION" 2>/dev/null || true
aws s3api put-public-access-block --bucket "$SOURCE_BUCKET" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true 2>/dev/null || true

# Zipper et uploader les sources
zip -r /tmp/source.zip . \
    -x ".git/*" "venv/*" "__pycache__/*" "*.pyc" ".kiro/*" \
    "infra/*" "tests/*" ".pytest_cache/*" ".vscode/*" "cdk.out/*" -q
aws s3 cp /tmp/source.zip "s3://${SOURCE_BUCKET}/source.zip" --quiet

# Lancer le build
BUILD_ID=$(aws codebuild start-build --project-name "$CODEBUILD_PROJECT" \
    --query 'build.id' --output text)
echo "  Build lance: $BUILD_ID"
echo "  Attente de la fin du build..."

while true; do
    STATUS=$(aws codebuild batch-get-builds --ids "$BUILD_ID" \
        --query 'builds[0].buildStatus' --output text)
    if [ "$STATUS" != "IN_PROGRESS" ]; then
        break
    fi
    sleep 10
    echo -n "."
done
echo ""

if [ "$STATUS" != "SUCCEEDED" ]; then
    echo "  ERREUR: Build echoue avec status $STATUS"
    exit 1
fi
echo "  Build reussi."

# --- Etape 4: Force ECS deployment ---
echo ""
echo "[4/4] Mise a jour du service ECS..."

CLUSTER=$(aws ecs list-clusters --query 'clusterArns[?contains(@, `TranscriptionCluster`)]' --output text)
SERVICE=$(aws ecs list-services --cluster "$CLUSTER" --query 'serviceArns[0]' --output text)
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
    --force-new-deployment --query 'service.serviceName' --output text

echo "  Deploiement ECS en cours (peut prendre 2-3 minutes)..."
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE" 2>/dev/null || true

# --- Resultat ---
echo ""
echo "=== Deploiement termine ==="
CF_URL=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontUrl`].OutputValue' --output text)
echo "URL: $CF_URL"
echo ""
