#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# setup_aws.sh - Script de configuração AWS para PortfolioESG
# ═══════════════════════════════════════════════════════════════════════════

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   PortfolioESG - Configuração AWS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Verificar AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI não encontrado!${NC}"
    echo "Instale com: brew install awscli"
    exit 1
fi

# Verificar credenciais
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ Credenciais AWS não configuradas!${NC}"
    echo "Execute: aws configure"
    exit 1
fi

echo -e "${GREEN}✅ AWS CLI configurado${NC}"
echo ""

# Solicitar informações
read -p "Nome do bucket S3 (ex: portfolioesg-app): " BUCKET_NAME
read -p "Região AWS (ex: sa-east-1): " REGION

if [ -z "$BUCKET_NAME" ] || [ -z "$REGION" ]; then
    echo -e "${RED}❌ Nome do bucket e região são obrigatórios${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Configurações:${NC}"
echo "  Bucket: $BUCKET_NAME"
echo "  Região: $REGION"
echo ""
read -p "Continuar? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ]; then
    echo "Cancelado."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
# 1. Criar Bucket S3
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[1/5] Criando bucket S3...${NC}"

if [ "$REGION" == "us-east-1" ]; then
    aws s3 mb s3://$BUCKET_NAME
else
    aws s3 mb s3://$BUCKET_NAME --region $REGION
fi

echo -e "${GREEN}✅ Bucket criado${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# 2. Configurar Website Estático
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[2/5] Configurando website estático...${NC}"

aws s3 website s3://$BUCKET_NAME \
    --index-document latest_run_summary.html \
    --error-document latest_run_summary.html

echo -e "${GREEN}✅ Website configurado${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# 3. Configurar Bucket Policy
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[3/5] Aplicando bucket policy...${NC}"

# Desbloquear acesso público
aws s3api put-public-access-block \
    --bucket $BUCKET_NAME \
    --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

# Criar policy
cat > /tmp/bucket-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$BUCKET_NAME/*"
        }
    ]
}
EOF

aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy file:///tmp/bucket-policy.json
rm /tmp/bucket-policy.json

echo -e "${GREEN}✅ Bucket policy aplicada${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# 4. Criar Usuário IAM para Deploy
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[4/5] Criando usuário IAM para GitHub Actions...${NC}"

IAM_USER="github-actions-portfolioesg"

# Criar usuário (ignora erro se já existe)
aws iam create-user --user-name $IAM_USER 2>/dev/null || true

# Criar policy
cat > /tmp/deploy-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::$BUCKET_NAME",
                "arn:aws:s3:::$BUCKET_NAME/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudfront:CreateInvalidation"
            ],
            "Resource": "*"
        }
    ]
}
EOF

aws iam put-user-policy \
    --user-name $IAM_USER \
    --policy-name S3DeployPolicy \
    --policy-document file:///tmp/deploy-policy.json

rm /tmp/deploy-policy.json

# Criar access keys
echo ""
echo -e "${YELLOW}Criando access keys...${NC}"
KEYS=$(aws iam create-access-key --user-name $IAM_USER --output json)

ACCESS_KEY=$(echo $KEYS | python3 -c "import sys, json; print(json.load(sys.stdin)['AccessKey']['AccessKeyId'])")
SECRET_KEY=$(echo $KEYS | python3 -c "import sys, json; print(json.load(sys.stdin)['AccessKey']['SecretAccessKey'])")

echo -e "${GREEN}✅ Usuário IAM criado${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# 5. Fazer Upload Inicial
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}[5/5] Fazendo upload inicial dos arquivos...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_DIR="$SCRIPT_DIR/../html"

if [ -d "$HTML_DIR" ]; then
    aws s3 sync "$HTML_DIR" s3://$BUCKET_NAME/ \
        --exclude "*.DS_Store" \
        --exclude "data/*.json" \
        --exclude "data/*.csv"
    echo -e "${GREEN}✅ Upload concluído${NC}"
else
    echo -e "${YELLOW}⚠️  Pasta html não encontrada, pulando upload${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Resumo Final
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 Configuração concluída!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 URLs:${NC}"
echo "   Website: http://$BUCKET_NAME.s3-website-$REGION.amazonaws.com"
echo ""
echo -e "${YELLOW}📋 Configure estes secrets no GitHub:${NC}"
echo ""
echo "   AWS_ACCESS_KEY_ID: $ACCESS_KEY"
echo "   AWS_SECRET_ACCESS_KEY: $SECRET_KEY"
echo "   AWS_REGION: $REGION"
echo "   S3_BUCKET: $BUCKET_NAME"
echo ""
echo -e "${RED}⚠️  IMPORTANTE: Guarde estas credenciais em local seguro!${NC}"
echo -e "${RED}   Elas não poderão ser recuperadas depois.${NC}"
echo ""
echo -e "${YELLOW}📋 Próximos passos:${NC}"
echo "   1. Configure os secrets no GitHub (Settings > Secrets > Actions)"
echo "   2. Configure autenticação Firebase (docs/SETUP_AUTH.md)"
echo "   3. Adicione domínio do S3/CloudFront no Firebase"
echo "   4. Faça push para main e o deploy será automático!"
echo ""
