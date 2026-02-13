#!/bin/bash
# setup_gcp.sh - Script de configuração inicial do GCP para PortfolioESG
#
# Uso: ./scripts/setup_gcp.sh [--project-id PROJECT_ID]
#
# Este script configura toda a infraestrutura necessária no Google Cloud Platform

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configurações padrão
PROJECT_ID="${PROJECT_ID:-portfolioesg-app}"
REGION="southamerica-east1"
ZONE="southamerica-east1-a"
WEBSITE_BUCKET="portfolioesg-website"
DATA_BUCKET="portfolioesg-data"
VM_NAME="portfolioesg-runner"
SA_NAME="github-actions-deploy"

# Diretório do projeto
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        -h|--help)
            echo "Uso: $0 [OPTIONS]"
            echo ""
            echo "Opções:"
            echo "  --project-id ID   ID do projeto GCP (default: portfolioesg-app)"
            exit 0
            ;;
        *)
            echo "Opção desconhecida: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}"
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  SETUP GCP - PortfolioESG"
echo "═══════════════════════════════════════════════════════════════════════════"
echo -e "${NC}"
echo ""
echo "  Project ID:     $PROJECT_ID"
echo "  Region:         $REGION"
echo "  Zone:           $ZONE"
echo "  Website Bucket: $WEBSITE_BUCKET"
echo "  Data Bucket:    $DATA_BUCKET"
echo ""

# Verificar se gcloud está instalado
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI não encontrado!${NC}"
    echo ""
    echo "Instale com: brew install --cask google-cloud-sdk"
    echo "Depois execute: gcloud init"
    exit 1
fi

# Verificar login
echo -e "${YELLOW}▶ Verificando autenticação...${NC}"
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo -e "${RED}❌ Não autenticado no gcloud${NC}"
    echo "Execute: gcloud auth login"
    exit 1
fi

CURRENT_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
echo -e "${GREEN}✓ Autenticado como: $CURRENT_ACCOUNT${NC}"

# Função para perguntar confirmação
confirm() {
    read -p "Continuar? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Criar/Selecionar Projeto
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 1: Projeto GCP"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

# Verificar se projeto existe
if gcloud projects describe $PROJECT_ID &> /dev/null; then
    echo -e "${GREEN}✓ Projeto '$PROJECT_ID' já existe${NC}"
else
    echo -e "${YELLOW}▶ Criando projeto '$PROJECT_ID'...${NC}"
    gcloud projects create $PROJECT_ID --name="PortfolioESG"
    echo -e "${GREEN}✓ Projeto criado${NC}"
fi

# Definir projeto padrão
gcloud config set project $PROJECT_ID
echo -e "${GREEN}✓ Projeto configurado como padrão${NC}"

# Verificar billing
echo ""
echo -e "${YELLOW}⚠️  IMPORTANTE: Verifique se o billing está habilitado!${NC}"
echo "   Vá em: https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID"
echo ""
if ! confirm; then
    echo "Setup cancelado."
    exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2: Habilitar APIs
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 2: Habilitando APIs"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

APIS=(
    "compute.googleapis.com"
    "storage.googleapis.com"
    "cloudscheduler.googleapis.com"
    "cloudfunctions.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "iam.googleapis.com"
    "run.googleapis.com"
)

for api in "${APIS[@]}"; do
    echo -e "${YELLOW}▶ Habilitando $api...${NC}"
    gcloud services enable $api --quiet
done
echo -e "${GREEN}✓ APIs habilitadas${NC}"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3: Criar Buckets
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 3: Criando Cloud Storage Buckets"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

# Website bucket
if gsutil ls -b gs://$WEBSITE_BUCKET &> /dev/null; then
    echo -e "${GREEN}✓ Bucket '$WEBSITE_BUCKET' já existe${NC}"
else
    echo -e "${YELLOW}▶ Criando bucket '$WEBSITE_BUCKET'...${NC}"
    gsutil mb -l $REGION gs://$WEBSITE_BUCKET
    gsutil web set -m index.html -e index.html gs://$WEBSITE_BUCKET
    echo -e "${GREEN}✓ Bucket website criado${NC}"
fi

# Data bucket
if gsutil ls -b gs://$DATA_BUCKET &> /dev/null; then
    echo -e "${GREEN}✓ Bucket '$DATA_BUCKET' já existe${NC}"
else
    echo -e "${YELLOW}▶ Criando bucket '$DATA_BUCKET'...${NC}"
    gsutil mb -l $REGION gs://$DATA_BUCKET
    echo -e "${GREEN}✓ Bucket data criado${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4: Criar Service Account para GitHub Actions
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 4: Criando Service Account para GitHub Actions"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SA_EMAIL &> /dev/null; then
    echo -e "${GREEN}✓ Service Account '$SA_NAME' já existe${NC}"
else
    echo -e "${YELLOW}▶ Criando Service Account...${NC}"
    gcloud iam service-accounts create $SA_NAME \
        --display-name="GitHub Actions Deploy"
    echo -e "${GREEN}✓ Service Account criada${NC}"
fi

# Adicionar permissões
echo -e "${YELLOW}▶ Configurando permissões...${NC}"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin" \
    --quiet

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/compute.instanceAdmin.v1" \
    --quiet

echo -e "${GREEN}✓ Permissões configuradas${NC}"

# Gerar chave JSON
KEY_FILE="$PROJECT_ROOT/gcp-sa-key.json"
if [ -f "$KEY_FILE" ]; then
    echo -e "${YELLOW}⚠️  Arquivo de chave já existe: $KEY_FILE${NC}"
else
    echo -e "${YELLOW}▶ Gerando chave JSON...${NC}"
    gcloud iam service-accounts keys create "$KEY_FILE" \
        --iam-account=$SA_EMAIL
    echo -e "${GREEN}✓ Chave salva em: $KEY_FILE${NC}"
    echo -e "${RED}⚠️  IMPORTANTE: Adicione este arquivo ao .gitignore!${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5: Upload inicial
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 5: Upload Inicial"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

echo "Deseja fazer upload dos arquivos agora?"
if confirm; then
    echo -e "${YELLOW}▶ Fazendo upload do website (html/)...${NC}"
    gsutil -m rsync -r -d "$PROJECT_ROOT/html" "gs://$WEBSITE_BUCKET"
    echo -e "${GREEN}✓ Website uploaded${NC}"

    echo -e "${YELLOW}▶ Fazendo upload dos parâmetros...${NC}"
    gsutil -m rsync -r "$PROJECT_ROOT/parameters" "gs://$DATA_BUCKET/parameters"
    echo -e "${GREEN}✓ Parâmetros uploaded${NC}"

    echo -e "${YELLOW}▶ Fazendo upload dos dados (results)...${NC}"
    if [ -d "$PROJECT_ROOT/data/results" ]; then
        gsutil -m rsync -r "$PROJECT_ROOT/data/results" "gs://$DATA_BUCKET/data/results"
        echo -e "${GREEN}✓ Dados uploaded${NC}"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6: Configurar acesso público ou IAP
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 6: Configuração de Acesso"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

echo "Como deseja configurar o acesso ao website?"
echo "  1) Público (qualquer pessoa pode acessar)"
echo "  2) Privado (configurar IAP manualmente depois)"
read -p "Escolha [1/2]: " access_choice

case "$access_choice" in
    1)
        echo -e "${YELLOW}▶ Configurando acesso público...${NC}"
        gsutil iam ch allUsers:objectViewer gs://$WEBSITE_BUCKET
        echo -e "${GREEN}✓ Bucket configurado como público${NC}"
        WEBSITE_URL="https://storage.googleapis.com/$WEBSITE_BUCKET/index.html"
        ;;
    *)
        echo -e "${YELLOW}▶ Mantendo bucket privado${NC}"
        echo "Para configurar IAP, siga as instruções em docs/GCP_DEPLOY.md"
        WEBSITE_URL="(configurar Load Balancer + IAP)"
        ;;
esac

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7: Criar VM (opcional)
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════"
echo "  STEP 7: Compute Engine VM"
echo -e "═══════════════════════════════════════════════════════════════════════════${NC}"

echo "Deseja criar a VM para processamento dos scripts?"
if confirm; then
    if gcloud compute instances describe $VM_NAME --zone=$ZONE &> /dev/null; then
        echo -e "${GREEN}✓ VM '$VM_NAME' já existe${NC}"
    else
        echo -e "${YELLOW}▶ Criando VM '$VM_NAME'...${NC}"

        echo "Tipo de VM:"
        echo "  1) Preemptível (mais barato, pode ser interrompida)"
        echo "  2) On-demand (mais caro, estável)"
        read -p "Escolha [1/2]: " vm_type

        PREEMPTIBLE_FLAG=""
        if [ "$vm_type" = "1" ]; then
            PREEMPTIBLE_FLAG="--preemptible"
        fi

        gcloud compute instances create $VM_NAME \
            --zone=$ZONE \
            --machine-type=e2-small \
            --image-family=ubuntu-2204-lts \
            --image-project=ubuntu-os-cloud \
            --boot-disk-size=20GB \
            --boot-disk-type=pd-standard \
            --tags=portfolioesg \
            --scopes=storage-full \
            $PREEMPTIBLE_FLAG

        echo -e "${GREEN}✓ VM criada${NC}"
        echo ""
        echo -e "${YELLOW}Para configurar a VM, execute:${NC}"
        echo "  gcloud compute ssh $VM_NAME --zone=$ZONE"
        echo ""
        echo "E siga as instruções em docs/GCP_DEPLOY.md Parte 3.2"
    fi
else
    echo "VM não criada. Execute manualmente quando necessário."
fi

# ═══════════════════════════════════════════════════════════════════════════
# RESUMO FINAL
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════════════"
echo "  ✅ SETUP COMPLETO!"
echo "═══════════════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  📦 Projeto GCP:      $PROJECT_ID"
echo "  🌐 Website Bucket:   gs://$WEBSITE_BUCKET"
echo "  💾 Data Bucket:      gs://$DATA_BUCKET"
echo "  🔑 Service Account:  $SA_EMAIL"
echo "  🗝️  Chave JSON:       $KEY_FILE"
echo "  🔗 Website URL:      $WEBSITE_URL"
echo ""
echo -e "${YELLOW}PRÓXIMOS PASSOS:${NC}"
echo ""
echo "  1. Adicione a chave ao .gitignore:"
echo "     echo 'gcp-sa-key.json' >> .gitignore"
echo ""
echo "  2. Configure os GitHub Secrets:"
echo "     - GCP_PROJECT_ID: $PROJECT_ID"
echo "     - GCP_SA_KEY: <conteúdo de $KEY_FILE>"
echo "     - GCS_BUCKET: $WEBSITE_BUCKET"
echo "     - GCS_DATA_BUCKET: $DATA_BUCKET"
echo ""
echo "  3. Crie o workflow em .github/workflows/deploy-gcp.yml"
echo "     (veja docs/GCP_DEPLOY.md)"
echo ""
echo "  4. Para IAP/autenticação, siga docs/GCP_DEPLOY.md Parte 5"
echo ""

