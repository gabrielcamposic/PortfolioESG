# PortfolioESG - Deploy GCP (Guia Atualizado)

Este guia documenta o deploy do PortfolioESG no Google Cloud Platform, incluindo:
- Otimização de storage (eliminação de CSVs individuais)
- VM Spot (preemptível) com suporte a checkpoint
- Firebase Hosting com domínio personalizado
- Autenticação via Google Identity

## Arquitetura Atualizada

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Google Cloud Platform                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────────────────────────────────────────┐  │
│   │   Cloud      │    │         Compute Engine (e2-small, Spot)          │  │
│   │   Scheduler  │───▶│  ┌─────────────────────────────────────────┐     │  │
│   │  22:00 BRT   │    │  │  gcp_vm_runner.sh                       │     │  │
│   └──────────────┘    │  │    ├─ Download → Direct to StockDataDB  │     │  │
│                       │  │    ├─ Scoring                            │     │  │
│                       │  │    ├─ Portfolio Optimization             │     │  │
│                       │  │    └─ Checkpoint on SIGTERM              │     │  │
│                       │  └─────────────────────────────────────────┘     │  │
│                       └──────────────────────────────────────────────────┘  │
│                                        │                                     │
│                                        ▼                                     │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                    Cloud Storage (GCS)                                │  │
│   │  ┌─────────────────────────────┐  ┌─────────────────────────────┐    │  │
│   │  │  portfolioesg-data/         │  │  portfolioesg-website/      │    │  │
│   │  │  ├─ findb/                  │  │  ├─ html/                   │    │  │
│   │  │  │  ├─ StockDataDB.csv      │  │  │  ├─ latest_run_summary/  │    │  │
│   │  │  │  ├─ FinancialsDB.csv     │  │  │  └─ meu_portfolio/       │    │  │
│   │  │  │  └─ skipped_tickers.json │  │  └─ data/                   │    │  │
│   │  │  ├─ results/                │  │     └─ portfolio_results.json│    │  │
│   │  │  └─ parameters/             │  └─────────────────────────────┘    │  │
│   │  └─────────────────────────────┘                                     │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                        │                                     │
│   ┌──────────────┐                     │                                     │
│   │   Firebase   │◀────────────────────┘                                     │
│   │   Hosting    │                                                           │
│   │  + Auth      │────▶ portfolio.arranjoconsultivo.com.br                   │
│   └──────────────┘                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Pré-requisitos Concluídos

- [x] Conta Google Cloud (gabrielcampos@icloud.com)
- [x] Projeto GCP criado (portfolioesg)
- [x] gcloud CLI instalado
- [x] Billing habilitado
- [x] APIs essenciais habilitadas

---

## Fase 1: Otimização de Storage (Local)

Antes do deploy, consolidar dados para reduzir storage em ~95%.

### 1.1 Executar Migração de Dados

```bash
cd ~/PortfolioESG

# Verificar o que será feito (dry run)
python scripts/migrate_findata_to_consolidated.py --dry-run

# Se satisfeito, executar migração com backup
python scripts/migrate_findata_to_consolidated.py

# Para realmente remover os CSVs individuais (após validação)
python scripts/migrate_findata_to_consolidated.py --remove-csvs
```

### 1.2 Habilitar Modo de Storage Direto

Editar `parameters/downpar.txt`:
```
storage_mode = direct
```

Este modo faz com que novos downloads sejam salvos diretamente no `StockDataDB.csv`, sem criar CSVs individuais.

### 1.3 Testar Pipeline Localmente

```bash
# Executar pipeline completo
./engines/A_Portfolio.sh

# Verificar se dados foram consolidados corretamente
ls -la data/findb/
```

---

## Fase 2: Configurar Cloud Storage

### 2.1 Criar Buckets

```bash
PROJECT_ID="portfolioesg"
REGION="southamerica-east1"

# Bucket para dados de processamento
gsutil mb -l $REGION gs://portfolioesg-data

# Bucket para website
gsutil mb -l $REGION gs://portfolioesg-website
```

### 2.2 Upload Inicial de Dados

```bash
# Upload dados consolidados (findb, não findata)
gsutil -m rsync -r ~/PortfolioESG/data/findb gs://portfolioesg-data/data/findb
gsutil -m rsync -r ~/PortfolioESG/data/results gs://portfolioesg-data/data/results
gsutil -m rsync -r ~/PortfolioESG/parameters gs://portfolioesg-data/parameters

# Upload website
gsutil -m rsync -r ~/PortfolioESG/html gs://portfolioesg-website
```

### 2.3 Habilitar Versionamento (Backup)

```bash
# Habilitar versionamento para backup automático
gsutil versioning set on gs://portfolioesg-data

# Configurar lifecycle para manter últimos 7 dias
cat > /tmp/lifecycle.json << 'EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "numNewerVersions": 7,
          "isLive": false
        }
      }
    ]
  }
}
EOF

gsutil lifecycle set /tmp/lifecycle.json gs://portfolioesg-data
```

---

## Fase 3: Configurar VM Spot

### 3.1 Criar VM Preemptível

```bash
VM_NAME="portfolioesg-runner"
ZONE="southamerica-east1-a"

gcloud compute instances create $VM_NAME \
  --zone=$ZONE \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-standard \
  --tags=portfolioesg \
  --scopes=storage-full,compute-rw \
  --provisioning-model=SPOT \
  --instance-termination-action=STOP \
  --no-restart-on-failure
```

### 3.2 Configurar VM

```bash
# Conectar à VM
gcloud compute ssh $VM_NAME --zone=$ZONE

# Instalar dependências
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git poppler-utils jq

# Clonar repositório
git clone https://github.com/gabrielcamposic/PortfolioESG.git
cd PortfolioESG

# Criar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate
pip install -r engines/requirements.txt

# Dar permissão de execução aos scripts
chmod +x scripts/gcp_vm_runner.sh
chmod +x scripts/gcp_runner.py
chmod +x engines/*.sh

# Testar runner (sem shutdown, sem sync)
./scripts/gcp_vm_runner.sh --no-shutdown --skip-sync
```

### 3.3 Criar Script de Startup

```bash
# Na VM, criar script de startup
sudo tee /opt/portfolioesg_startup.sh << 'EOF'
#!/bin/bash
# Startup script for PortfolioESG VM

cd /home/$(ls /home | head -1)/PortfolioESG
./scripts/gcp_vm_runner.sh >> /var/log/portfolioesg_startup.log 2>&1
EOF

sudo chmod +x /opt/portfolioesg_startup.sh
```

---

## Fase 4: Cloud Scheduler

### 4.1 Criar Cloud Function para Iniciar VM

```bash
# Criar pasta para a function
mkdir -p /tmp/start-vm-function && cd /tmp/start-vm-function

# Criar main.py
cat > main.py << 'EOF'
import functions_framework
from googleapiclient import discovery
from google.auth import default

@functions_framework.http
def start_vm(request):
    """Start the PortfolioESG Spot VM."""
    credentials, project = default()
    compute = discovery.build('compute', 'v1', credentials=credentials)
    
    zone = 'southamerica-east1-a'
    instance = 'portfolioesg-runner'
    
    result = compute.instances().start(
        project=project,
        zone=zone,
        instance=instance
    ).execute()
    
    return f'VM start initiated: {result.get("id", "unknown")}'
EOF

# Criar requirements.txt
cat > requirements.txt << 'EOF'
functions-framework==3.*
google-api-python-client==2.*
google-auth==2.*
EOF

# Deploy
gcloud functions deploy start-portfolioesg-vm \
  --gen2 \
  --runtime=python311 \
  --region=southamerica-east1 \
  --source=. \
  --entry-point=start_vm \
  --trigger-http \
  --no-allow-unauthenticated
```

### 4.2 Criar Job no Cloud Scheduler

```bash
# Job diário às 22:00 (após fechamento B3)
gcloud scheduler jobs create http portfolioesg-daily-run \
  --location=southamerica-east1 \
  --schedule="0 22 * * 1-5" \
  --time-zone="America/Sao_Paulo" \
  --uri="https://southamerica-east1-portfolioesg.cloudfunctions.net/start-portfolioesg-vm" \
  --http-method=POST \
  --oidc-service-account-email="portfolioesg@appspot.gserviceaccount.com"
```

---

## Fase 5: Firebase Hosting com Domínio Personalizado

### 5.1 Configurar Firebase

```bash
# Instalar Firebase CLI
npm install -g firebase-tools

# Login
firebase login

# Inicializar Firebase no projeto
cd ~/PortfolioESG
firebase init hosting

# Selecionar projeto existente: portfolioesg
# Public directory: html
# Single-page app: No
# Automatic builds: No
```

### 5.2 Configurar firebase.json

```json
{
  "hosting": {
    "public": "html",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "/projetos/PortfolioESG",
        "destination": "/latest_run_summary.html"
      },
      {
        "source": "/projetos/PortfolioESG/portfolio",
        "destination": "/meu_portfolio.html"
      }
    ],
    "headers": [
      {
        "source": "**/*.json",
        "headers": [
          {"key": "Cache-Control", "value": "no-cache, max-age=0"}
        ]
      }
    ]
  }
}
```

### 5.3 Configurar Domínio no Cloudflare

1. No Cloudflare, adicionar registro CNAME:
   - **Name**: `portfolio`
   - **Target**: `portfolioesg.web.app`
   - **Proxy status**: DNS only (grey cloud) para funcionar com Firebase

2. No Firebase Console:
   - Ir em Hosting > Custom domains
   - Adicionar: `portfolio.arranjoconsultivo.com.br`
   - Seguir instruções para verificação

### 5.4 Deploy para Firebase

```bash
# Deploy
firebase deploy --only hosting

# URL será: portfolio.arranjoconsultivo.com.br
```

---

## Fase 6: Autenticação com Firebase Auth

### 6.1 Habilitar Google Sign-In

No Firebase Console:
1. Authentication > Sign-in method
2. Habilitar Google provider
3. Adicionar domínio autorizado: `portfolio.arranjoconsultivo.com.br`

### 6.2 Configurar Domínio no OAuth

No Google Cloud Console:
1. APIs & Services > Credentials
2. OAuth consent screen > Add domain: `arranjoconsultivo.com.br`

---

## Estimativa de Custos (Mensal)

| Componente | Uso Estimado | Custo |
|------------|--------------|-------|
| Compute Engine Spot | ~1h/dia × 22 dias | ~$2.50 |
| Cloud Storage | ~200MB | ~$0.05 |
| Cloud Scheduler | 22 jobs/mês | ~$0.10 |
| Cloud Functions | 22 invocações | ~$0.00 |
| Firebase Hosting | ~1GB transfer | Gratuito |
| **Total** | | **~$3/mês** |

---

## Comandos Úteis

```bash
# Verificar status da VM
gcloud compute instances describe portfolioesg-runner --zone=southamerica-east1-a

# Conectar à VM
gcloud compute ssh portfolioesg-runner --zone=southamerica-east1-a

# Ver logs da última execução
gsutil cat gs://portfolioesg-data/logs/gcp_vm_runner.log

# Ver checkpoint (para debug)
gsutil cat gs://portfolioesg-data/data/run_checkpoint.json

# Forçar execução manual
gcloud scheduler jobs run portfolioesg-daily-run --location=southamerica-east1

# Parar VM manualmente
gcloud compute instances stop portfolioesg-runner --zone=southamerica-east1-a
```

---

## Troubleshooting

### VM foi preemptida durante execução

O sistema salva checkpoint automaticamente. Na próxima execução:
1. Cloud Scheduler inicia a VM
2. gcp_vm_runner.sh baixa checkpoint do GCS
3. gcp_runner.py retoma do último estágio bem-sucedido

### Download falhou para alguns tickers

Verifique `data/findb/skipped_tickers.json` para ver quais tickers foram marcados como inválidos.

### Firebase mostra dados antigos

Os arquivos JSON têm Cache-Control: no-cache, mas o browser pode cachear. Force refresh com Ctrl+Shift+R.

