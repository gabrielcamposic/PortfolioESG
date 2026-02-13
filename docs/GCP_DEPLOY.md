# PortfolioESG - Deploy no Google Cloud Platform

Este documento descreve como hospedar o PortfolioESG no GCP com deploy automático via GitHub Actions.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Google Cloud Platform                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────────────────────────────────────────┐  │
│   │   Cloud      │    │            Compute Engine (e2-small)             │  │
│   │   Scheduler  │───▶│  ┌─────────────────────────────────────────┐     │  │
│   │  (Cron Job)  │    │  │  A_Portfolio.sh → Download/Score/Optim  │     │  │
│   └──────────────┘    │  │  B_Ledger.sh    → Process Notes         │     │  │
│                       │  │  C_OptimizedPortfolio.sh → Rebalancing  │     │  │
│                       │  └─────────────────────────────────────────┘     │  │
│                       └──────────────────────────────────────────────────┘  │
│                                        │                                     │
│                                        ▼                                     │
│   ┌──────────────┐    ┌──────────────────────────────────────────────────┐  │
│   │   Identity   │◀───│             Cloud Storage (GCS)                  │  │
│   │   Aware      │    │  ┌─────────────┐  ┌─────────────────────────┐    │  │
│   │   Proxy      │    │  │   html/     │  │       data/             │    │  │
│   │   (IAP)      │    │  │  (Website)  │  │  (findata, results)     │    │  │
│   └──────────────┘    │  └─────────────┘  └─────────────────────────┘    │  │
│         │             └──────────────────────────────────────────────────┘  │
│         │                              │                                     │
│         ▼                              │                                     │
│   ┌──────────────┐                     │                                     │
│   │  Cloud CDN   │◀────────────────────┘                                     │
│   │  (opcional)  │                                                           │
│   └──────────────┘                                                           │
│         │                                                                    │
└─────────│────────────────────────────────────────────────────────────────────┘
          │
          ▼
    ┌──────────────┐
    │   Usuário    │
    │ (gabrielcampos│
    │ @icloud.com) │
    └──────────────┘

GitHub ─────▶ GitHub Actions ─────▶ Deploy automático para GCS
```

## Pré-requisitos

- [x] Conta Google Cloud (gabrielcampos@icloud.com)
- [ ] Projeto GCP criado
- [ ] gcloud CLI instalado
- [ ] Billing habilitado no projeto

---

## Parte 1: Configuração Inicial do GCP

### 1.1 Instalar Google Cloud CLI

```bash
# macOS com Homebrew
brew install --cask google-cloud-sdk

# Inicializar e fazer login
gcloud init
# Siga as instruções para autenticar com gabrielcampos@icloud.com
```

### 1.2 Criar Projeto GCP

```bash
# Defina variáveis
PROJECT_ID="portfolioesg-app"
REGION="southamerica-east1"  # São Paulo
ZONE="southamerica-east1-a"

# Criar projeto
gcloud projects create $PROJECT_ID --name="PortfolioESG"

# Definir projeto padrão
gcloud config set project $PROJECT_ID

# Habilitar billing (necessário fazer via Console)
echo "⚠️  Vá em https://console.cloud.google.com/billing e vincule o projeto a uma conta de faturamento"
```

### 1.3 Habilitar APIs Necessárias

```bash
gcloud services enable \
  compute.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudfunctions.googleapis.com \
  iap.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com
```

---

## Parte 2: Cloud Storage (Website Estático)

### 2.1 Criar Bucket para Website

```bash
BUCKET_NAME="portfolioesg-website"

# Criar bucket na região de São Paulo
gsutil mb -l $REGION gs://$BUCKET_NAME

# Configurar como website
gsutil web set -m index.html -e index.html gs://$BUCKET_NAME
```

### 2.2 Configurar Permissões

**Opção A: Público (simples, sem autenticação)**
```bash
# Tornar público (APENAS se não precisar de autenticação)
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME
```

**Opção B: Privado com IAP (recomendado - autenticação Google)**
```bash
# Manter privado e usar Identity-Aware Proxy
# Configure via Console: 
# Security > Identity-Aware Proxy > Enable
```

### 2.3 Criar Bucket para Dados (Processamento)

```bash
DATA_BUCKET="portfolioesg-data"

# Criar bucket para dados de processamento
gsutil mb -l $REGION gs://$DATA_BUCKET

# Manter privado (padrão)
```

### 2.4 Fazer Upload Inicial

```bash
# Upload do website (html/)
gsutil -m rsync -r -d /Users/gabrielcampos/PortfolioESG/html gs://$BUCKET_NAME

# Upload dos dados necessários
gsutil -m rsync -r /Users/gabrielcampos/PortfolioESG/data gs://$DATA_BUCKET/data
gsutil -m rsync -r /Users/gabrielcampos/PortfolioESG/parameters gs://$DATA_BUCKET/parameters
```

---

## Parte 3: Compute Engine (Processamento)

### 3.1 Criar VM para Execução dos Scripts

```bash
VM_NAME="portfolioesg-runner"

# Criar VM com e2-small (suficiente baseado na análise de recursos)
gcloud compute instances create $VM_NAME \
  --zone=$ZONE \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-standard \
  --tags=portfolioesg \
  --scopes=storage-full \
  --preemptible  # Usar VM preemptível para economizar (~60% mais barato)

# Para produção estável (sem interrupções), remova --preemptible
```

### 3.2 Configurar VM

```bash
# Conectar à VM
gcloud compute ssh $VM_NAME --zone=$ZONE

# Dentro da VM, executar:
sudo apt update && sudo apt upgrade -y

# Instalar dependências
sudo apt install -y python3-pip python3-venv git poppler-utils

# Clonar repositório (ou baixar do GCS)
git clone https://github.com/SEU_USUARIO/PortfolioESG.git
cd PortfolioESG

# Criar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências Python
pip install -r engines/requirements.txt

# Criar script de sincronização
cat > sync_and_run.sh << 'EOF'
#!/bin/bash
set -e

PROJECT_DIR="/home/$USER/PortfolioESG"
DATA_BUCKET="gs://portfolioesg-data"
WEBSITE_BUCKET="gs://portfolioesg-website"

# Sincronizar dados do GCS
gsutil -m rsync -r $DATA_BUCKET/data $PROJECT_DIR/data
gsutil -m rsync -r $DATA_BUCKET/parameters $PROJECT_DIR/parameters

# Executar pipeline
cd $PROJECT_DIR
source .venv/bin/activate
./engines/A_Portfolio.sh

# Sincronizar resultados de volta
gsutil -m rsync -r $PROJECT_DIR/html/data $WEBSITE_BUCKET/data
gsutil -m rsync -r $PROJECT_DIR/data/results $DATA_BUCKET/data/results

echo "Pipeline completed at $(date)"
EOF

chmod +x sync_and_run.sh
```

### 3.3 Criar Script de Startup/Shutdown

```bash
# Script para iniciar, executar e parar a VM automaticamente
cat > /home/$USER/run_and_shutdown.sh << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/portfolioesg.log"

echo "$(date): Starting PortfolioESG pipeline" >> $LOG_FILE

# Executar pipeline
/home/$USER/PortfolioESG/sync_and_run.sh >> $LOG_FILE 2>&1

echo "$(date): Pipeline finished, shutting down" >> $LOG_FILE

# Desligar a VM para economizar
sudo shutdown -h now
EOF

chmod +x /home/$USER/run_and_shutdown.sh
```

---

## Parte 4: Cloud Scheduler (Agendamento)

### 4.1 Criar Cloud Function para Iniciar VM

```bash
# Criar pasta para a function
mkdir -p /tmp/start-vm-function
cd /tmp/start-vm-function

# Criar main.py
cat > main.py << 'EOF'
import functions_framework
from googleapiclient import discovery
from google.auth import default

@functions_framework.http
def start_vm(request):
    """Start the PortfolioESG VM."""
    credentials, project = default()
    
    compute = discovery.build('compute', 'v1', credentials=credentials)
    
    zone = 'southamerica-east1-a'
    instance = 'portfolioesg-runner'
    
    result = compute.instances().start(
        project=project,
        zone=zone,
        instance=instance
    ).execute()
    
    return f'VM start initiated: {result}'
EOF

# Criar requirements.txt
cat > requirements.txt << 'EOF'
functions-framework==3.*
google-api-python-client==2.*
google-auth==2.*
EOF

# Deploy da function
gcloud functions deploy start-portfolioesg-vm \
  --gen2 \
  --runtime=python311 \
  --region=$REGION \
  --source=. \
  --entry-point=start_vm \
  --trigger-http \
  --allow-unauthenticated=false
```

### 4.2 Criar Job no Cloud Scheduler

```bash
# Criar job para executar diariamente às 22:00 (horário de Brasília)
gcloud scheduler jobs create http portfolioesg-daily-run \
  --location=$REGION \
  --schedule="0 22 * * 1-5" \
  --time-zone="America/Sao_Paulo" \
  --uri="https://$REGION-$PROJECT_ID.cloudfunctions.net/start-portfolioesg-vm" \
  --http-method=POST \
  --oidc-service-account-email="$PROJECT_ID@appspot.gserviceaccount.com"
```

---

## Parte 5: Identity-Aware Proxy (Autenticação Google)

### 5.1 Configurar Load Balancer + IAP

```bash
# Esta configuração é feita via Console para maior controle
echo "
═══════════════════════════════════════════════════════════════
  CONFIGURAÇÃO DO IAP (Console)
═══════════════════════════════════════════════════════════════

1. Vá em: https://console.cloud.google.com/net-services/loadbalancing

2. Criar Load Balancer HTTP(S):
   - Nome: portfolioesg-lb
   - Frontend:
     * Protocolo: HTTPS
     * Criar certificado gerenciado pelo Google (ou use seu domínio)
   - Backend:
     * Bucket: portfolioesg-website
     * Enable Cloud CDN: Sim

3. Configurar IAP:
   - Vá em: Security > Identity-Aware Proxy
   - Ative IAP para o backend
   - Adicione gabrielcampos@icloud.com como membro com role 'IAP-secured Web App User'

4. Configurar OAuth Consent Screen (se necessário):
   - Vá em: APIs & Services > OAuth consent screen
   - User Type: External (ou Internal se for Workspace)
   - Preencha os campos obrigatórios
"
```

### 5.2 Script de Configuração Automatizada (alternativa)

```bash
# Se preferir automatizar via CLI:
# Criar backend bucket para load balancer
gcloud compute backend-buckets create portfolioesg-backend \
  --gcs-bucket-name=$BUCKET_NAME \
  --enable-cdn

# Criar URL map
gcloud compute url-maps create portfolioesg-lb \
  --default-backend-bucket=portfolioesg-backend

# Criar certificado SSL gerenciado (requer domínio)
# gcloud compute ssl-certificates create portfolioesg-cert \
#   --domains=seudominio.com

# Para usar sem domínio personalizado, configure via Console
```

---

## Parte 6: GitHub Actions (CI/CD)

### 6.1 Criar Service Account para Deploy

```bash
# Criar service account
SA_NAME="github-actions-deploy"
gcloud iam service-accounts create $SA_NAME \
  --display-name="GitHub Actions Deploy"

SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

# Dar permissões necessárias
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/compute.instanceAdmin.v1"

# Criar chave JSON
gcloud iam service-accounts keys create ~/gcp-key.json \
  --iam-account=$SA_EMAIL

# IMPORTANTE: Guarde o conteúdo deste arquivo para o GitHub Secrets
cat ~/gcp-key.json
```

### 6.2 Configurar GitHub Secrets

Vá em: Repository > Settings > Secrets and variables > Actions

| Secret Name | Valor |
|-------------|-------|
| `GCP_PROJECT_ID` | `portfolioesg-app` |
| `GCP_SA_KEY` | Conteúdo completo do arquivo `gcp-key.json` |
| `GCS_BUCKET` | `portfolioesg-website` |
| `GCS_DATA_BUCKET` | `portfolioesg-data` |

### 6.3 Criar Workflow do GitHub Actions

```bash
mkdir -p .github/workflows
```

Criar arquivo `.github/workflows/deploy-gcp.yml`:

```yaml
name: Deploy to GCP

on:
  push:
    branches: [main]
    paths:
      - 'html/**'
      - 'parameters/**'
  workflow_dispatch:  # Permite trigger manual

env:
  PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  BUCKET_NAME: ${{ secrets.GCS_BUCKET }}
  DATA_BUCKET: ${{ secrets.GCS_DATA_BUCKET }}

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    permissions:
      contents: read
      id-token: write
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      
      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
        with:
          project_id: ${{ env.PROJECT_ID }}
      
      - name: Deploy HTML to GCS
        run: |
          gsutil -m rsync -r -d html/ gs://${{ env.BUCKET_NAME }}/
      
      - name: Deploy Parameters to GCS
        run: |
          gsutil -m rsync -r parameters/ gs://${{ env.DATA_BUCKET }}/parameters/
      
      - name: Invalidate CDN Cache (if configured)
        run: |
          # Se estiver usando Cloud CDN, invalide o cache
          # gcloud compute url-maps invalidate-cdn-cache portfolioesg-lb \
          #   --path="/*" --async
          echo "Deploy completed successfully!"
```

---

## Parte 7: Fluxo de Desenvolvimento

### 7.1 Workflow Diário

```bash
# 1. Fazer alterações localmente
# ... edite arquivos ...

# 2. Testar localmente
cd html && python -m http.server 8000

# 3. Commit e push
git add .
git commit -m "Descrição da mudança"
git push

# 4. GitHub Actions faz deploy automático para GCS! 🚀
```

### 7.2 Executar Pipeline Manualmente

```bash
# Opção 1: Via Console
# Vá em: Compute Engine > VM instances > portfolioesg-runner > Start

# Opção 2: Via CLI
gcloud compute instances start portfolioesg-runner --zone=southamerica-east1-a

# Opção 3: Trigger Cloud Scheduler manualmente
gcloud scheduler jobs run portfolioesg-daily-run --location=$REGION
```

### 7.3 Verificar Logs

```bash
# Logs da VM
gcloud compute ssh portfolioesg-runner --zone=$ZONE --command="cat /var/log/portfolioesg.log"

# Logs do Cloud Scheduler
gcloud logging read "resource.type=cloud_scheduler_job" --limit=10

# Logs da Cloud Function
gcloud functions logs read start-portfolioesg-vm --region=$REGION
```

---

## Parte 8: Custos Estimados (USD/mês)

### Cenário: 22 execuções/mês (dias úteis)

| Serviço | Detalhes | Custo Estimado |
|---------|----------|----------------|
| **Compute Engine** | e2-small preemptível, ~10min/exec | ~$0.50 |
| **Cloud Storage** | ~2GB website + ~1GB dados | ~$0.07 |
| **Cloud Functions** | 22 invocações/mês | ~$0.00 (free tier) |
| **Cloud Scheduler** | 1 job | ~$0.00 (3 grátis) |
| **Cloud CDN** (opcional) | ~1GB transfer | ~$0.10 |
| **Load Balancer + IAP** | Forwarding rule | ~$18.00* |
| **Total sem LB/IAP** | | **~$0.70/mês** |
| **Total com LB/IAP** | | **~$18.70/mês** |

*O Load Balancer tem custo fixo. Alternativa mais barata:
- Usar Cloud Run para servir website (~$0-2/mês)
- Manter bucket público sem IAP

### Alternativa Econômica: Firebase Hosting

```bash
# Se preferir hospedagem estática mais barata com auth
# Firebase Hosting + Firebase Auth = ~$0/mês para uso pessoal

npm install -g firebase-tools
firebase login
firebase init hosting
firebase deploy
```

---

## Parte 9: Comandos Úteis

### Gerenciar VM

```bash
# Listar VMs
gcloud compute instances list

# Iniciar VM
gcloud compute instances start portfolioesg-runner --zone=southamerica-east1-a

# Parar VM
gcloud compute instances stop portfolioesg-runner --zone=southamerica-east1-a

# Conectar via SSH
gcloud compute ssh portfolioesg-runner --zone=southamerica-east1-a
```

### Gerenciar Storage

```bash
# Listar buckets
gsutil ls

# Ver conteúdo do bucket
gsutil ls -la gs://portfolioesg-website/

# Fazer upload manual
gsutil -m rsync -r html/ gs://portfolioesg-website/

# Download de dados
gsutil -m rsync -r gs://portfolioesg-data/data/ ./data/
```

### Monitorar Custos

```bash
# Ver billing no Console
echo "Vá em: https://console.cloud.google.com/billing"

# Criar alerta de orçamento (recomendado)
# Vá em: Billing > Budgets & alerts > Create budget
# Configure alerta para $10/mês
```

---

## Parte 10: Checklist de Deploy

- [ ] 1. Instalar gcloud CLI
- [ ] 2. Fazer login: `gcloud auth login`
- [ ] 3. Criar projeto: `gcloud projects create portfolioesg-app`
- [ ] 4. Vincular billing ao projeto
- [ ] 5. Habilitar APIs necessárias
- [ ] 6. Criar buckets GCS
- [ ] 7. Criar VM Compute Engine
- [ ] 8. Configurar VM com scripts
- [ ] 9. Configurar Cloud Scheduler
- [ ] 10. Criar Service Account para GitHub
- [ ] 11. Configurar GitHub Secrets
- [ ] 12. Criar workflow GitHub Actions
- [ ] 13. Fazer primeiro deploy
- [ ] 14. Configurar IAP (opcional)
- [ ] 15. Criar alertas de billing

---

## Troubleshooting

### "Permission denied" ao acessar bucket
```bash
# Verificar permissões
gsutil iam get gs://portfolioesg-website

# Adicionar permissão
gsutil iam ch user:gabrielcampos@icloud.com:objectViewer gs://portfolioesg-website
```

### VM não inicia automaticamente
```bash
# Verificar logs do Scheduler
gcloud logging read "resource.type=cloud_scheduler_job" --limit=5

# Verificar logs da Cloud Function
gcloud functions logs read start-portfolioesg-vm --region=southamerica-east1
```

### Pipeline falha na VM
```bash
# Conectar e ver logs
gcloud compute ssh portfolioesg-runner --zone=southamerica-east1-a
cat /var/log/portfolioesg.log
tail -100 /home/$USER/PortfolioESG/logs/*.log
```

### Deploy do GitHub Actions falha
1. Verifique os secrets configurados
2. Verifique se a service account tem permissões
3. Veja os logs em: Repository > Actions > [workflow run]

---

## Próximos Passos (Melhorias Futuras)

1. **Cloud Run**: Migrar website para Cloud Run (mais flexível)
2. **Secret Manager**: Armazenar credenciais sensíveis
3. **Cloud Monitoring**: Criar dashboards de monitoramento
4. **Cloud Build**: Migrar de GitHub Actions para Cloud Build
5. **Artifact Registry**: Criar imagem Docker do ambiente

